"""RAW preprocessing, per-session empirical-line calibration and week-two QA."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .config import asset_path, load_config, plane_roi, sample_roi
from .export import save_multiband
from .images import pair_jpegs, read_jpeg, read_jpeg_metadata
from .output import stage_output
from .radiometry import RelativeCorrector, analysis_eligibility, load_settings
from .raw import decode_raw, split_bayer_channels
from .reflectance import apply_reflectance, fit_empirical_line, validate_timepoints
from .vignetting import correct_vignetting

RAW_EXTENSIONS = {'.raw', '.dng', '.cr2', '.cr3', '.nef', '.arw', '.raf', '.orf', '.rw2'}
INPUT_EXTENSIONS = RAW_EXTENSIONS | {'.npy'}
CHANNELS = ('R', 'G1', 'G2', 'B')
JPEG_EXTENSIONS = {'.jpg', '.jpeg'}


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
            warnings.append('Black level is unknown; zero offset assumed')
        if any(metadata['saturated_fraction'].values()):
            warnings.append('Pixels at the encoding/decoder white limit are masked as NaN')
        metadata['vignetting_corrected'] = self.flat_channels is not None
        metadata['warnings'] = warnings
        return planes, metadata


def save_frame(output_dir: Path, planes: dict[str, np.ndarray], metadata: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / '.gitignore').write_text('*\n', encoding='utf-8')
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
    metadata['export'] = save_multiband(output_dir, planes, metadata, metadata.get('filter', 'RGN'))
    write_json(output_dir / 'metadata.json', metadata)


def save_jpeg_preview(path: Path, output_dir: Path) -> dict:
    planes, metadata = read_jpeg(path)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / '.gitignore').write_text('*\n', encoding='utf-8')
    rgb = np.stack([planes['R'], planes['G1'], planes['B']], axis=-1)
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(output_dir / 'preview.png')
    metadata.update({'status': 'preview_only', 'analysis_eligibility': analysis_eligibility(source_encoding='JPEG'),
                     'quantitative_input': False,
                     'reason': 'Project document 02 section 4: JPEG is for preview, quantitative work uses RAW'})
    write_json(output_dir / 'metadata.json', metadata)
    return metadata


def check_camera_identity(camera: dict, filter_name: str, expected_model: str) -> None:
    model = camera.get('model')
    declared_filters = [camera.get('filter')]
    if isinstance(model, str) and '_' in model:
        suffix = model.rsplit('_', 1)[1]
        if suffix in {'RGN', 'OCN', 'RGB', 'NGB', 'NIR', 'RE'}:
            declared_filters.append(suffix)
    for declared_filter in declared_filters:
        if declared_filter is not None and declared_filter != filter_name:
            raise ValueError(f'Camera filter {declared_filter} conflicts with {filter_name}; never mix RGN and OCN')
    if model is not None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError('Camera model must be a nonempty string when supplied')
        normalized_model = model.removeprefix('MAPIR ').strip()
        if not normalized_model.startswith(expected_model):
            raise ValueError(f'Lens profile {expected_model} does not match camera {model}')


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


def _run_batch(input_path: Path, output_dir: Path, *, config_path: Path | None = None,
              pattern: str | None = None, settings_path: Path | None = None, mode: str = 'auto') -> dict:
    input_path, output_dir = input_path.resolve(), output_dir.resolve()
    if not input_path.exists():
        raise ValueError(f'Input does not exist: {input_path}')
    root = input_path if input_path.is_dir() else input_path.parent
    if output_dir.is_relative_to(root) or root.is_relative_to(output_dir):
        raise ValueError('Output must be separate from the input directory; source images stay unchanged')
    if output_dir.exists():
        raise ValueError('Output directory already exists; choose a new --output directory')
    if mode not in ('auto', 'relative', 'panel'):
        raise ValueError('mode must be auto, relative or panel')
    if mode == 'relative' and config_path is not None:
        raise ValueError('Choose relative mode or a panel calibration config, not both')
    if config_path is None and mode != 'relative' and input_path.is_dir() and (root / 'calibration.json').is_file():
        config_path = root / 'calibration.json'
    if mode == 'panel' and config_path is None:
        raise ValueError('Panel mode requires --calibration or INPUT/calibration.json')
    panel_mode = config_path is not None
    settings = load_settings(settings_path)
    config = load_config(config_path)
    config_pattern = config.get('pattern')
    if pattern and config_pattern and pattern != config_pattern:
        raise ValueError('--pattern conflicts with calibration config')
    filter_name = config.get('filter', settings['filter']) if panel_mode else settings['filter']
    # Only inspect the declared camera identity. Private field notes/GPS are not copied.
    if input_path.is_dir() and (root / 'metadata.json').is_file():
        survey = json.loads((root / 'metadata.json').read_text(encoding='utf-8-sig'))
        if not isinstance(survey, dict) or not isinstance(survey.get('camera', {}), dict):
            raise ValueError('Survey metadata must contain a camera object')
        check_camera_identity(survey.get('camera', {}), filter_name, settings['camera_model'])
    preprocessor = Preprocessor(pattern or config_pattern, config.get('black_level'),
                                asset_path(root, config['flat']) if config.get('flat') else None)
    corrector = RelativeCorrector(settings) if not panel_mode else None
    candidates = sorted(p.resolve() for p in (root.rglob('*') if input_path.is_dir() else [input_path])
                        if p.is_file() and p.suffix.lower() in INPUT_EXTENSIONS | JPEG_EXTENSIONS)
    if any(not p.is_relative_to(root) for p in candidates):
        raise ValueError('Input image links must stay inside the input directory')
    sessions, mapping, models, checks = config.get('sessions', []), {}, {}, {}
    excluded = {preprocessor.flat_path} if preprocessor.flat_path else set()
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
            image, object_id = asset_path(root, check['image']), check['object_id']
            if not isinstance(object_id, str) or not object_id or object_id in seen_objects:
                raise ValueError(f'{name}: each check needs a unique, nonempty object_id')
            seen_objects.add(object_id)
            if image == target or image not in matched:
                raise ValueError(f'{name}: check must use a separate scene image belonging to the session')
            checks.setdefault(image, []).append(check)
    if excluded & set(mapping):
        raise ValueError('Scene patterns must exclude calibration targets and flat fields')
    raw_files = [p for p in candidates if p.suffix.lower() in INPUT_EXTENSIONS]
    jpeg_files = [p for p in candidates if p.suffix.lower() in JPEG_EXTENSIONS]
    pairs, unpaired_jpegs, pair_reasons = pair_jpegs(
        [p for p in raw_files if p.suffix.lower() != '.npy'], jpeg_files, settings['max_jpeg_delta_seconds'])
    files = [p for p in raw_files if p not in excluded] + unpaired_jpegs
    if not files:
        raise ValueError('No RAW/NPY or JPEG inputs found')
    if set(mapping) - set(files):
        raise ValueError('Calibration session contains scene images outside this run input')
    output_dir.mkdir(parents=True)
    # Every run carries its own ignore rule, including arbitrary --output paths.
    (output_dir / '.gitignore').write_text('*\n', encoding='utf-8')
    summary = {'schema_version': 2, 'mode': 'panel' if panel_mode else 'relative',
               'source_file_count': len(candidates), 'input_count': len(files),
               'raw_count': len([p for p in raw_files if p not in excluded]), 'jpeg_count': len(jpeg_files),
               'paired_jpeg_count': sum(p not in excluded for p in pairs),
               'processed_count': 0, 'failed_count': 0, 'relative_corrected_count': 0,
               'preview_only_count': 0, 'exposure_normalized_count': 0, 'factory_flat_corrected_count': 0,
               'low_signal_count': 0,
               'calibrated_count': 0, 'filter': filter_name, 'calibration': models, 'frames': [],
               'software_settings': settings, 'analysis_eligibility': analysis_eligibility(),
               'absolute_reflectance_accuracy': {'status': 'not_measured', 'below_5_percent_verified': False}}
    measurements = {(mapping[image], check['object_id']):
                    {'session': mapping[image], 'object_id': check['object_id'], 'means': {}}
                    for image, image_checks in checks.items() for check in image_checks}
    manifest = {'schema_version': 1, 'stage': 'week2_radiometry', 'coordinate_system': 'sensor_pixels',
                'georeferenced': False, 'filter': filter_name, 'analysis_eligibility': analysis_eligibility(),
                'software_settings': settings, 'items': []}
    for image in files:
        relative = image.relative_to(root)
        destination = output_dir / relative.parent / (relative.name.replace('.', '_') + '_processed')
        entry = {'source': relative.as_posix(), 'output': destination.relative_to(output_dir).as_posix()}
        try:
            if image.suffix.lower() in JPEG_EXTENSIONS:
                metadata = save_jpeg_preview(image, destination)
                metadata['source'] = relative.as_posix()
                write_json(destination / 'metadata.json', metadata)
                entry.update({'status': 'preview_only', 'warnings': metadata['warnings']})
                summary['preview_only_count'] += 1
            else:
                planes, metadata = preprocessor.read(image)
                capture = {}
                if image in pairs:
                    capture = read_jpeg_metadata(pairs[image])
                    if (capture['width'], capture['height']) != (metadata.get('width'), metadata.get('height')):
                        raise ValueError('Paired RAW and JPEG geometry do not match; exposure pairing rejected')
                    check_camera_identity(capture, filter_name, settings['camera_model'])
                metadata['capture'] = {key: capture.get(key) for key in
                                       ('exposure_seconds', 'iso', 'model', 'datetime_original', 'orientation')}
                metadata['source_jpeg'] = pairs[image].relative_to(root).as_posix() if image in pairs else None
                metadata['jpeg_association'] = pair_reasons.get(image, 'not_applicable')
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
                    metadata.update({'status': 'calibrated', 'units': 'reflectance_fraction', 'calibration': model,
                                     'analysis_eligibility': analysis_eligibility(certified=True)})
                    metadata['out_of_range_fraction'] = {
                        key: float(np.mean((plane < 0) | (plane > 1))) for key, plane in planes.items()}
                    for check in checks.get(image, []):
                        pending_records.append({'session': name, 'object_id': check['object_id'],
                                                'means': {key: sample_roi(plane, check['roi']) for key, plane in planes.items()}})
                elif corrector is not None:
                    planes, metadata = corrector.apply(planes, metadata, capture)
                else:
                    metadata.update({'status': 'uncalibrated', 'units': 'digital_number',
                                     'analysis_eligibility': analysis_eligibility()})
                    metadata['warnings'].append('Reflectance not calibrated: no session/target assigned')
                save_frame(destination, planes, metadata)
                for record in pending_records:
                    measurements[(record['session'], record['object_id'])] = record
                entry.update({'status': metadata['status'], 'warnings': metadata['warnings']})
                summary['calibrated_count'] += int(name is not None)
                summary['relative_corrected_count'] += int(metadata['status'] == 'relative_corrected')
                summary['exposure_normalized_count'] += int(metadata.get('correction', {}).get('exposure_normalized', False))
                summary['factory_flat_corrected_count'] += int(metadata.get('correction', {}).get('factory_flat_applied', False))
                summary['low_signal_count'] += int('low_signal' in metadata.get('quality', {}).get('flags', []))
            item = {'source': relative.as_posix(), 'status': metadata['status'], 'units': metadata['units'],
                    'preview': (destination / 'preview.png').relative_to(output_dir).as_posix(),
                    'metadata': (destination / 'metadata.json').relative_to(output_dir).as_posix(),
                    'analysis_eligibility': metadata['analysis_eligibility']}
            if metadata.get('quality'):
                item['quality'] = metadata['quality']
            if metadata.get('export'):
                item.update({key: (destination / metadata['export'][key]).relative_to(output_dir).as_posix()
                             for key in ('raster', 'valid_mask')})
                item.update({'bands': metadata['export']['bands'], 'georeferenced': False, 'nodata': 'NaN'})
            manifest['items'].append(item)
            summary['processed_count'] += 1
        except (ValueError, RuntimeError, OSError) as exc:
            entry.update({'status': 'failed', 'error': str(exc)})
            summary['failed_count'] += 1
        summary['frames'].append(entry)
        print(f"[{len(summary['frames'])}/{len(files)}] {relative}: {entry['status']}", flush=True)
    summary['status'] = ('failed' if summary['failed_count'] else
                         'preview_only' if summary['raw_count'] == 0 else
                         'relative_corrected' if not panel_mode else
                         'calibrated' if summary['calibrated_count'] == summary['raw_count'] else
                         'partially_calibrated' if summary['calibrated_count'] else 'uncalibrated')
    summary['validation'] = validate_timepoints(list(measurements.values()), [session['id'] for session in sessions])
    summary['validation']['scope'] = 'Independent same-object repeatability; not factory profile fit error or absolute accuracy'
    summary['handoff_manifest'] = 'manifest.json'
    write_json(output_dir / 'manifest.json', manifest)
    write_json(output_dir / 'summary.json', summary)
    return summary


def run_batch(input_path: Path, output_dir: Path, *, config_path: Path | None = None,
              pattern: str | None = None, settings_path: Path | None = None, mode: str = 'auto',
              require_validation: bool = False) -> dict:
    with stage_output(input_path, output_dir) as transaction:
        summary = _run_batch(input_path, transaction['path'], config_path=config_path,
                             pattern=pattern, settings_path=settings_path, mode=mode)
        rejected = summary['failed_count'] > 0 or (require_validation and summary['validation']['status'] != 'passed')
        publish = not transaction['existed'] or not rejected
        summary['output_updated'] = publish
        summary['previous_output_retained'] = not publish
        if publish:
            write_json(transaction['path'] / 'summary.json', summary)
        transaction['publish'] = publish
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
