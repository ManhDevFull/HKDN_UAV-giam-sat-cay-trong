"""RAW preprocessing, per-session empirical-line calibration and week-two QA."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .config import asset_path, load_config, plane_roi, sample_roi
from .raw import decode_raw, split_bayer_channels
from .reflectance import apply_reflectance, fit_empirical_line, validate_timepoints
from .vignetting import correct_vignetting

RAW_EXTENSIONS = {'.raw', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf', '.orf', '.rw2'}
INPUT_EXTENSIONS = RAW_EXTENSIONS | {'.npy'}
CHANNELS = ('R', 'G1', 'G2', 'B')


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def read_mosaic(path: Path, pattern: str | None = None) -> tuple[np.ndarray, dict]:
    if path.suffix.lower() == '.npy':
        try:
            mosaic = np.load(path, allow_pickle=False)
        except EOFError as exc:
            raise ValueError(f'{path.name}: NPY input is empty or truncated') from exc
        metadata = {'source': path.name, 'pattern': pattern or 'RGGB', 'white_level': None,
                    'black_levels': None, 'decoder': 'numpy'}
    else:
        mosaic, metadata = decode_raw(path)
    if not np.issubdtype(mosaic.dtype, np.number) or np.iscomplexobj(mosaic) or not np.all(np.isfinite(mosaic)):
        raise ValueError(f'{path.name}: mosaic must contain finite real numbers')
    inferred = metadata.get('pattern')
    if pattern and inferred and pattern != inferred:
        raise ValueError(f'{path.name}: configured pattern {pattern} conflicts with decoder pattern {inferred}')
    metadata['pattern'] = pattern or inferred or 'RGGB'
    return mosaic, metadata


class Preprocessor:
    def __init__(self, pattern: str | None = None, black_level: float | None = None, flat: Path | None = None):
        self.pattern = pattern
        self.black_level = black_level
        self.flat_path = flat
        self.flat_channels = None
        self.flat_pattern = None
        if flat is not None:
            self.flat_channels, info = self._read(flat)
            self.flat_pattern = info['pattern']
            for channel in self.flat_channels.values():
                if not np.all(np.isfinite(channel)) or np.any(channel <= 0):
                    raise ValueError('Flat field must be unsaturated and positive after black subtraction')

    def _read(self, path: Path) -> tuple[dict[str, np.ndarray], dict]:
        mosaic, metadata = read_mosaic(path, self.pattern)
        planes = split_bayer_channels(mosaic, metadata['pattern'])
        black_levels = metadata.get('black_levels') or {}
        offsets = {}
        fractions = {}
        white = metadata.get('white_level')
        for name, plane in planes.items():
            offset = self.black_level if self.black_level is not None else black_levels.get(name, 0.0)
            offsets[name] = float(offset)
            invalid = plane >= white if white is not None else np.zeros(plane.shape, dtype=bool)
            fractions[name] = float(np.mean(invalid))
            signal = np.maximum(plane.astype(np.float32) - offset, 0)
            signal[invalid] = np.nan
            planes[name] = signal
        metadata['black_offsets_applied'] = offsets
        metadata['black_level_source'] = ('configuration' if self.black_level is not None else
                                          'decoder' if black_levels else 'unknown; zero offset assumed')
        metadata['saturated_fraction'] = fractions
        return planes, metadata

    def read(self, path: Path) -> tuple[dict[str, np.ndarray], dict]:
        planes, metadata = self._read(path)
        warnings = list(metadata.get('warnings', []))
        if self.flat_channels is None:
            warnings.append('Vignetting not corrected: no measured flat field supplied')
        else:
            if metadata['pattern'] != self.flat_pattern:
                raise ValueError('Flat field and scene must use the same Bayer pattern')
            planes = {name: correct_vignetting(plane, self.flat_channels[name]) for name, plane in planes.items()}
        if metadata['black_level_source'].startswith('unknown'):
            warnings.append('Black level is unknown; zero offset assumed (empirical-line intercept is fitted)')
        if any(metadata['saturated_fraction'].values()):
            warnings.append('Pixels at the encoding/decoder white limit are masked as NaN')
        metadata['vignetting_corrected'] = self.flat_channels is not None
        metadata['warnings'] = warnings
        return planes, metadata


def save_frame(output_dir: Path, planes: dict[str, np.ndarray], metadata: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, plane in planes.items():
        np.save(output_dir / f'{name}.npy', plane.astype(np.float32))
    # Preview values are stretched; quantitative data stay linear in the NPY files.
    rgb = np.stack([planes['R'], (planes['G1'] + planes['G2']) / 2, planes['B']], axis=-1)
    valid = rgb[np.isfinite(rgb)]
    high = float(np.percentile(valid[::16], 99)) if valid.size else 1.0
    preview = np.nan_to_num(np.clip(rgb / max(high, 1e-6), 0, 1), nan=0.0)
    # Native half-resolution: RAW ROI coordinates = 2 * preview coordinates.
    Image.fromarray((preview * 255).astype(np.uint8)).save(output_dir / 'preview.png')
    metadata['channels'] = {}
    for name, plane in planes.items():
        finite = plane[np.isfinite(plane)]
        metadata['channels'][name] = {
            'shape': list(plane.shape), 'valid_fraction': float(finite.size / plane.size),
            'min': float(finite.min()) if finite.size else None,
            'max': float(finite.max()) if finite.size else None,
        }
    write_json(output_dir / 'metadata.json', metadata)


def _references(panel: dict, filter_name: str) -> dict[str, float]:
    values = panel.get('reflectance', {})
    third = 'NIR' if filter_name == 'RGN' else 'B'
    if not isinstance(values, dict) or set(values) != {'R', 'G', third}:
        raise ValueError(f'Panel reflectance must contain exactly R, G and {third} (fractions 0..1)')
    return {'R': values['R'], 'G1': values['G'], 'G2': values['G'], 'B': values[third]}


def calibrate_session(session: dict, root: Path, preprocessor: Preprocessor, filter_name: str) -> tuple[dict, Path]:
    target = asset_path(root, session.get('target'))
    planes, metadata = preprocessor.read(target)
    samples = {name: [] for name in CHANNELS}
    references = {name: [] for name in CHANNELS}
    rectangles = []
    for panel in session['panels']:
        if not isinstance(panel, dict) or set(panel) != {'roi', 'reflectance'}:
            raise ValueError('Each panel must contain roi and reflectance')
        roi = panel['roi']
        plane_roi(roi, planes['R'].shape)
        x, y, w, h = roi
        if any(x < a + c and a < x + w and y < b + d and b < y + h for a, b, c, d in rectangles):
            raise ValueError('Calibration panel ROIs must not overlap')
        rectangles.append(roi)
        reference = _references(panel, filter_name)
        for name in CHANNELS:
            samples[name].append(sample_roi(planes[name], roi))
            references[name].append(reference[name])
    return {'coefficients': fit_empirical_line(samples, references),
            'target': target.relative_to(root).as_posix(),
            'method': 'empirical line: reflectance = gain * corrected_DN + offset',
            'target_pattern': metadata['pattern'], 'warnings': metadata['warnings'],
            'exposure_confirmed_by_operator': True}, target


def run_batch(input_path: Path, output_dir: Path, *, config_path: Path | None = None,
              pattern: str | None = None) -> dict:
    input_path = input_path.resolve()
    output_dir = output_dir.resolve()
    if not input_path.exists():
        raise ValueError(f'Input does not exist: {input_path}')
    root = input_path if input_path.is_dir() else input_path.parent
    if output_dir.is_relative_to(root) or root.is_relative_to(output_dir):
        raise ValueError('Output must be separate from the input directory; source images stay unchanged')
    if output_dir.exists():
        raise ValueError('Output directory already exists; choose a new --output directory')
    if config_path is None and input_path.is_dir() and (root / 'calibration.json').is_file():
        config_path = root / 'calibration.json'
    config = load_config(config_path)
    config_pattern = config.get('pattern')
    if pattern and config_pattern and pattern != config_pattern:
        raise ValueError('--pattern conflicts with calibration config')
    preprocessor = Preprocessor(pattern or config_pattern, config.get('black_level'),
                                asset_path(root, config['flat']) if config.get('flat') else None)
    candidates = sorted(p.resolve() for p in (root.rglob('*') if input_path.is_dir() else [input_path])
                        if p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS)
    sessions = config.get('sessions', [])
    filter_name = config.get('filter', 'RGN')
    mapping = {}
    models = {}
    excluded = {preprocessor.flat_path} if preprocessor.flat_path else set()
    checks = {}
    for session in sessions:
        name = session['id']
        model, target = calibrate_session(session, root, preprocessor, filter_name)
        models[name] = model
        excluded.add(target)
        matched = set()
        for glob in session['images']:
            matches = {p.resolve() for p in root.glob(glob) if p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS}
            if not matches:
                raise ValueError(f'{name}: no RAW/NPY images match {glob}')
            matched |= matches
        for image in matched:
            if not image.is_relative_to(root):
                raise ValueError('Scene paths must stay inside the input directory')
            if image in mapping:
                raise ValueError(f'Image belongs to more than one session: {image.name}')
            mapping[image] = name
        seen_objects = set()
        for check in session.get('checks', []):
            if not isinstance(check, dict) or set(check) != {'image', 'object_id', 'roi'}:
                raise ValueError('Each check must contain image, object_id and roi')
            image = asset_path(root, check['image'])
            object_id = check['object_id']
            if not isinstance(object_id, str) or not object_id or object_id in seen_objects:
                raise ValueError(f'{name}: each check needs a unique, nonempty object_id')
            seen_objects.add(object_id)
            if image == target or image not in matched:
                raise ValueError(f'{name}: check must use a separate scene image belonging to the session')
            checks.setdefault(image, []).append(check)
    if excluded & set(mapping):
        raise ValueError('Scene patterns must exclude calibration targets and flat fields')
    files = [p for p in candidates if p not in excluded]
    if not files:
        raise ValueError('No RAW/NPY scene images found (JPEGs are previews, not linear calibration inputs)')
    if set(mapping) - set(files):
        raise ValueError('Calibration session contains scene images outside this run input')
    output_dir.mkdir(parents=True)
    summary = {'schema_version': 1, 'input_count': len(files), 'processed_count': 0, 'failed_count': 0,
               'calibrated_count': 0, 'filter': filter_name, 'calibration': models, 'frames': []}
    # Expected checks remain present if decoding or ROI sampling fails, so a
    # completely missing validation object can never disappear from the report.
    measurements = {(mapping[image], check['object_id']):
                    {'session': mapping[image], 'object_id': check['object_id'], 'means': {}}
                    for image, image_checks in checks.items() for check in image_checks}
    for image in files:
        relative = image.relative_to(root)
        destination = output_dir / relative.parent / (relative.name.replace('.', '_') + '_processed')
        entry = {'source': relative.as_posix(), 'output': destination.relative_to(output_dir).as_posix()}
        try:
            planes, metadata = preprocessor.read(image)
            name = mapping.get(image)
            metadata.update({'source': relative.as_posix(), 'session': name, 'filter': filter_name,
                             'band_mapping': {'R': 'nominal_red', 'G1': 'nominal_green', 'G2': 'nominal_green',
                                              'B': 'nominal_NIR' if filter_name == 'RGN' else 'blue'}})
            if filter_name == 'RGN':
                metadata['warnings'].append('RGN spectral overlap is not unmixed; CFA planes are nominal bands')
            pending_records = []
            if name is not None:
                model = models[name]
                if metadata['pattern'] != model['target_pattern']:
                    raise ValueError('Target and scene Bayer patterns must match')
                planes = {key: apply_reflectance(plane, model['coefficients'][key]) for key, plane in planes.items()}
                metadata['status'] = 'calibrated'
                metadata['units'] = 'reflectance_fraction'
                metadata['calibration'] = model
                metadata['out_of_range_fraction'] = {
                    key: float(np.mean((plane < 0) | (plane > 1))) for key, plane in planes.items()}
                for check in checks.get(image, []):
                    pending_records.append({'session': name, 'object_id': check['object_id'],
                                            'means': {key: sample_roi(plane, check['roi']) for key, plane in planes.items()}})
            else:
                metadata['status'] = 'uncalibrated'
                metadata['units'] = 'digital_number'
                metadata['warnings'].append('Reflectance not calibrated: no session/target assigned')
            save_frame(destination, planes, metadata)
            for record in pending_records:
                measurements[(record['session'], record['object_id'])] = record
            entry.update({'status': metadata['status'], 'warnings': metadata['warnings']})
            summary['processed_count'] += 1
            summary['calibrated_count'] += int(name is not None)
        except (ValueError, RuntimeError, OSError) as exc:
            entry.update({'status': 'failed', 'error': str(exc)})
            summary['failed_count'] += 1
        summary['frames'].append(entry)
        print(f"[{len(summary['frames'])}/{len(files)}] {relative}: {entry['status']}", flush=True)
    summary['status'] = ('failed' if summary['failed_count'] else
                         'calibrated' if summary['calibrated_count'] == len(files) else
                         'partially_calibrated' if summary['calibrated_count'] else 'uncalibrated')
    summary['validation'] = validate_timepoints(list(measurements.values()), [session['id'] for session in sessions])
    summary['validation']['scope'] = 'Temporal repeatability of independent same-object ROIs; not absolute accuracy or fit residuals'
    write_json(output_dir / 'summary.json', summary)
    return summary


def process_mosaic(mosaic: np.ndarray, output_dir: Path, pattern: str = 'RGGB') -> dict:
    """Compatibility helper for week-one synthetic data (no implicit flat field)."""
    planes = {name: plane.astype(np.float32) for name, plane in split_bayer_channels(mosaic, pattern).items()}
    metadata = {'pattern': pattern, 'status': 'uncalibrated', 'units': 'digital_number',
                'vignetting_corrected': False}
    save_frame(output_dir, planes, metadata)
    return metadata


def process_raw(input_path: Path, output_dir: Path, pattern: str | None = None) -> dict:
    planes, metadata = Preprocessor(pattern).read(input_path)
    metadata.update({'status': 'uncalibrated', 'units': 'digital_number'})
    save_frame(output_dir, planes, metadata)
    return metadata
