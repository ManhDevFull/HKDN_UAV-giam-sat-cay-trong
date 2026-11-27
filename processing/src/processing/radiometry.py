"""Factory lens correction and exposure normalization, without a reflectance claim."""

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
from pathlib import Path

import numpy as np
from numpy.polynomial.chebyshev import chebvander


def load_settings(path: Path | None = None) -> dict:
    payload = (path.read_bytes() if path else
               files('processing').joinpath('profiles/default.json').read_bytes())
    settings = json.loads(payload.decode('utf-8-sig'))
    if (not isinstance(settings, dict) or type(settings.get('schema_version')) is not int
            or settings['schema_version'] != 1):
        raise ValueError('Settings require schema_version: 1')
    expected = {'schema_version', 'profile_id', 'camera_model', 'filter', 'lens_profile',
                'reference_exposure_seconds', 'reference_iso', 'raw_black_level',
                'normalize_exposure', 'max_jpeg_delta_seconds', 'min_signal_fraction'}
    if set(settings) != expected:
        raise ValueError('Settings must contain exactly the fields in profiles/default.json')
    if settings['camera_model'] != 'Survey3W' or settings['filter'] not in ('RGN', 'RGB'):
        raise ValueError('This software profile supports Survey3W RGN/RGB only; never mix RGN and OCN')
    if settings['lens_profile'] not in (None, 'survey3w.json'):
        raise ValueError('lens_profile must be survey3w.json or null')
    if type(settings['normalize_exposure']) is not bool:
        raise ValueError('normalize_exposure must be true or false')
    if not isinstance(settings['profile_id'], str) or not settings['profile_id'].strip():
        raise ValueError('profile_id must be a nonempty string')
    for key in ('reference_exposure_seconds', 'reference_iso'):
        value = settings[key]
        if type(value) not in (int, float) or not np.isfinite(value) or value <= 0:
            raise ValueError(f'{key} must be finite and positive')
    for key in ('raw_black_level', 'max_jpeg_delta_seconds'):
        value = settings[key]
        if type(value) not in (int, float) or not np.isfinite(value) or value < 0:
            raise ValueError(f'{key} must be finite and nonnegative')
    value = settings['min_signal_fraction']
    if type(value) not in (int, float) or not np.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('min_signal_fraction must be a fraction in [0,1]')
    settings['settings_sha256'] = hashlib.sha256(payload).hexdigest()
    return settings


def load_lens_profile() -> dict:
    return json.loads(files('processing').joinpath('profiles/survey3w.json').read_text(encoding='utf-8'))


def evaluate_lens(profile: dict, shape: tuple[int, int], pattern: str) -> dict[str, np.ndarray]:
    """Evaluate the original sensor geometry at the four Bayer sampling phases."""
    height, width = profile['sensor_shape']
    if shape != (height // 2, width // 2) or pattern not in ('RGGB', 'BGGR', 'GBRG', 'GRBG'):
        raise ValueError('Lens profile requires its native RAW geometry and an RGB Bayer pattern')
    result = {}
    green_index = 0
    for index, color in enumerate(pattern):
        row, column = divmod(index, 2)
        x = 2 * np.arange(column, width, 2, dtype=np.float64) / (width - 1) - 1
        y = 2 * np.arange(row, height, 2, dtype=np.float64) / (height - 1) - 1
        coefficients = np.asarray(profile['channels'][color]['coefficients'], dtype=np.float64)
        if coefficients.ndim != 2 or not np.all(np.isfinite(coefficients)):
            raise ValueError('Lens coefficients must be a finite 2D matrix')
        x_basis = chebvander(x, coefficients.shape[0] - 1)
        y_basis = chebvander(y, coefficients.shape[1] - 1)
        attenuation = (y_basis @ coefficients.T @ x_basis.T).astype(np.float32)
        if np.any(~np.isfinite(attenuation)) or np.any(attenuation <= 0):
            raise ValueError('Lens profile must predict finite, positive attenuation')
        name = color
        if color == 'G':
            green_index += 1
            name = f'G{green_index}'
        result[name] = attenuation
    return result


def analysis_eligibility(*, certified: bool = False, source_encoding: str = 'RAW') -> dict:
    return {'quantitative_input': certified and source_encoding == 'RAW',
            'required_quantitative_source': 'RAW', 'source_encoding': source_encoding,
            'absolute_reflectance': certified,
            'cross_survey_comparison': False, 'ndvi_time_series': False,
            'red_edge_available': False,
            'reason': ('Certified panels supplied; independent QA and spectral correction still required'
                       if certified else 'No measured reflectance/illumination reference; project document 02 sections 3-4')}


class RelativeCorrector:
    def __init__(self, settings: dict, lens_profile: dict | None = None):
        self.settings = settings
        self.profile = (lens_profile if lens_profile is not None else load_lens_profile()) if settings['lens_profile'] else None
        self._maps = {}

    def apply(self, planes: dict[str, np.ndarray], metadata: dict,
              capture: dict | None = None) -> tuple[dict[str, np.ndarray], dict]:
        """Preserve band ratios: apply one exposure factor, with no histogram matching."""
        if metadata.get('decoder') == 'pillow-jpeg':
            raise ValueError('JPEG is preview-only according to project document 02')
        info = deepcopy(metadata)
        warnings = info.setdefault('warnings', [])
        result = {name: np.asarray(plane, dtype=np.float32).copy() for name, plane in planes.items()}
        white = info.get('white_level')
        quality_flags = []
        signal_high = None
        if white is not None and white > 0:
            samples = [plane[::8, ::8] for plane in result.values()]
            valid = [sample[np.isfinite(sample)] for sample in samples]
            levels = [float(np.percentile(sample, 90)) / white for sample in valid if sample.size]
            if levels:
                signal_high = max(levels)
                if signal_high < self.settings['min_signal_fraction']:
                    quality_flags.append('low_signal')
                    warnings.append('Very low RAW signal; software correction cannot recover missing scene detail')
            else:
                quality_flags.append('no_valid_pixels')
        factory_applied = False
        if info.get('decoder') == 'mapir-survey3-packed12' and info.get('black_level_source', '').startswith('unknown'):
            offset = self.settings['raw_black_level']
            result = {name: np.maximum(plane - offset, 0) for name, plane in result.items()}
            info['black_offsets_applied'] = {name: offset for name in result}
            info['black_level_source'] = 'software settings; zero default is unmeasured'
        if self.profile is not None and not info.get('vignetting_corrected', False):
            shape = result['R'].shape
            if (info.get('decoder') == 'mapir-survey3-packed12'
                    and shape == tuple(n // 2 for n in self.profile['sensor_shape'])):
                pattern = info['pattern']
                key = (shape, pattern)
                if key not in self._maps:
                    self._maps[key] = evaluate_lens(self.profile, shape, pattern)
                result = {name: plane / self._maps[key][name] for name, plane in result.items()}
                factory_applied = True
                warnings = [warning for warning in warnings if not warning.startswith('Vignetting not corrected:')]
                warnings.append('Factory lens profile is not an individual-camera flat measurement')
            else:
                warnings.append('Factory lens correction skipped: input is not native Survey3W RAW geometry')
        capture = capture or {}
        factor = 1.0
        exposure_applied = False
        exposure, iso = capture.get('exposure_seconds'), capture.get('iso')
        if self.settings['normalize_exposure']:
            if (isinstance(exposure, (int, float)) and not isinstance(exposure, bool)
                    and np.isfinite(exposure) and exposure > 0 and iso == self.settings['reference_iso']):
                factor = self.settings['reference_exposure_seconds'] / exposure
                exposure_applied = True
            else:
                warnings.append('Exposure normalization skipped: no reliable paired exposure/ISO or unsupported ISO')
        denominator = float(white) if white is not None and white > 0 else 1.0
        result = {name: (plane * (factor / denominator)).astype(np.float32) for name, plane in result.items()}
        warnings.append('Relative signal only: changing sunlight and RGN spectral overlap are not calibrated')
        info.update({'status': 'relative_corrected', 'units': 'relative_signal' if denominator != 1 else 'relative_DN',
                     'warnings': warnings, 'vignetting_corrected': info.get('vignetting_corrected', False) or factory_applied,
                     'analysis_eligibility': analysis_eligibility(),
                     'quality': {'flags': quality_flags, 'raw_p90_fraction': signal_high,
                                 'low_signal_threshold': self.settings['min_signal_fraction']},
                     'correction': {'method': 'factory_flat_and_exposure', 'settings_id': self.settings['profile_id'],
                                    'settings_sha256': self.settings['settings_sha256'],
                                    'factory_flat_applied': factory_applied,
                                    'lens_profile_id': self.profile['profile_id'] if factory_applied else None,
                                    'exposure_normalized': exposure_applied, 'exposure_factor': factor,
                                    'reference_exposure_seconds': self.settings['reference_exposure_seconds'],
                                    'encoding_denominator': denominator, 'spectral_unmixing_applied': False},
                     'absolute_reflectance_accuracy': {'status': 'not_measured', 'below_5_percent_verified': False}})
        if factory_applied:
            info['correction']['lens_profile_validation'] = {
                name: value['validation'] for name, value in self.profile['channels'].items()}
        return result, info
