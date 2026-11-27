"""Prepare linear RAW-derived R/G/NIR TIFFs for a shared ODM reconstruction."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
import re

import numpy as np
from PIL import Image
import tifffile

from agriscan.io.raw_reader import read_raw
from processing.images import pair_jpegs, read_jpeg_metadata
from processing.radiometry import RelativeCorrector, load_settings
from processing.raw import split_bayer_channels


def _gps(path: Path) -> dict | None:
    def degrees(value):
        degree, minute, second = map(float, value)
        if degree < 0 or not 0 <= minute < 60 or not 0 <= second < 60:
            raise ValueError('Invalid GPS degrees/minutes/seconds')
        return degree + minute / 60 + second / 3600
    try:
        with Image.open(path) as image:
            exif = image.getexif()
            gps = exif.get_ifd(34853) if 34853 in exif else {}
        latitude, longitude = degrees(gps[2]), degrees(gps[4])
        if gps[1] in ('S', b'S'):
            latitude *= -1
        elif gps[1] not in ('N', b'N'):
            return None
        if gps[3] in ('W', b'W'):
            longitude *= -1
        elif gps[3] not in ('E', b'E'):
            return None
        altitude = float(gps[6])
        altitude_reference = gps.get(5, 0)
        if altitude_reference not in (0, 1, b'\x00', b'\x01'):
            return None
        if altitude_reference in (1, b'\x01'):
            altitude *= -1
        if not np.isfinite([latitude, longitude, altitude]).all() or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return None
        if latitude == 0 and longitude == 0:
            return None
        return {'longitude': longitude, 'latitude': latitude, 'altitude': altitude}
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError, OverflowError, OSError, SyntaxError):
        return None


def _capture_day(path: Path, capture: dict) -> str | None:
    timestamp = capture.get('datetime_original')
    if timestamp is not None:
        try:
            return datetime.fromisoformat(timestamp).date().isoformat()
        except (TypeError, ValueError):
            return None
    match = re.fullmatch(r'(\d{4}_\d{4}_\d{6})_\d+', path.stem)
    if match is not None:
        try:
            return datetime.strptime(match[1], '%Y_%m%d_%H%M%S').date().isoformat()
        except ValueError:
            return None
    return None


def prepare_images(survey_dir: Path, output_dir: Path, metadata: dict, config: dict) -> dict:
    camera = metadata['camera']
    if camera.get('filter') != 'RGN' or camera.get('model') not in ('MAPIR Survey3W', 'Survey3W', 'Survey3W_RGN'):
        raise ValueError('This pipeline requires verified MAPIR Survey3W RGN data; do not mix RGN/OCN/RGB')
    settings = load_settings()
    corrector = RelativeCorrector(settings)
    raws = sorted(p for p in (survey_dir / 'raw').rglob('*') if p.is_file() and p.suffix.lower() == '.raw')
    jpegs = sorted(p for p in (survey_dir / 'raw').rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg'))
    if not raws:
        raise ValueError('No RAW files in input/raw; JPG cannot be used as a quantitative raster')
    pairs, _, reasons = pair_jpegs(raws, jpegs, max_delta_seconds=settings['max_jpeg_delta_seconds'])
    image_dir = output_dir / 'images'
    image_dir.mkdir(parents=True)
    records, positions, rejected = [], {}, []
    capture_days = set()
    scale = config.get('mosaicking', {}).get('common_scale', 16384)
    for number, path in enumerate(raws, 1):
        mosaic, info = read_raw(path, survey_metadata=metadata)
        pattern = info.get('cfa_pattern')
        if pattern != 'RGGB':
            raise ValueError(f'{path.name}: unverified Bayer pattern')
        channels = split_bayer_channels(mosaic, pattern)
        planes = {name: np.maximum(plane.astype(np.float32) - settings['raw_black_level'], 0) for name, plane in channels.items()}
        for name, plane in channels.items():
            planes[name][plane >= info['white_level']] = np.nan
        capture = read_jpeg_metadata(pairs[path]) if path in pairs else {}
        if capture.get('model') not in (None, 'Survey3W_RGN'):
            raise ValueError(f'{path.name}: paired JPG model conflicts with Survey3W RGN')
        if capture and (capture['width'], capture['height']) != (mosaic.shape[1], mosaic.shape[0]):
            raise ValueError(f'{path.name}: paired JPG and RAW dimensions do not match')
        native = dict(info, decoder='mapir-survey3-packed12', pattern=pattern,
                      black_level_source='workflow settings', vignetting_corrected=False, warnings=[])
        planes, correction = corrector.apply(planes, native, capture)
        record = {'source': path.relative_to(survey_dir).as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'jpeg_association': reasons[path], 'correction': correction['correction'],
                  'quality': correction['quality'], 'warnings': correction['warnings']}
        position = _gps(pairs[path]) if path in pairs else None
        if any(flag in correction['quality']['flags'] for flag in ('low_signal', 'no_valid_pixels')):
            rejected.append(dict(record, reason='unusable_signal', quality_flags=correction['quality']['flags']))
            continue
        if position is None:
            rejected.append(dict(record, reason='missing_valid_GPS'))
            continue
        stack = np.stack([planes['R'], (planes['G1'] + planes['G2']) / 2, planes['B']], axis=-1)
        valid = np.isfinite(stack).all(axis=-1)
        record['joint_valid_fraction'] = float(np.count_nonzero(valid) / valid.size)
        record['sensor_saturation_fraction'] = info['pixel_stats']['saturated_ratio']
        if not np.any(valid):
            rejected.append(dict(record, reason='no_jointly_valid_spectral_pixels'))
            continue
        if not np.all(valid):
            record['warnings'].append('Invalid/saturated RAW pixels are encoded as zero; ODM interpolation near these pixels is not quantitatively verified')
        if np.any(stack[valid] * scale > 65535):
            rejected.append(dict(record, reason='common_scale_overflow; lower mosaicking.common_scale'))
            continue
        capture_day = _capture_day(path, capture)
        if capture_day is not None and capture_days and capture_day not in capture_days:
            raise ValueError('Usable RAW images span multiple capture days; split them into separate surveys before mosaicking')
        if capture_day is not None:
            capture_days.add(capture_day)
        record['capture_day'] = capture_day
        # Zero marks invalid RAW pixels; valid zeros are also conservatively masked.
        encoded = np.clip(np.nan_to_num(stack, nan=0) * scale, 0, 65535).round().astype(np.uint16)
        encoded[~valid] = 0
        name = f'frame_{number:05d}.tif'
        description = json.dumps({'bands': ['red', 'green', 'nir'], 'scale': scale,
                                  'units': 'relative_signal', 'source': record['source']})
        tifffile.imwrite(image_dir / name, encoded, photometric='rgb', metadata=None,
                         description=description,
                         extratags=[(271, 's', 0, 'MAPIR', False), (272, 's', 0, 'Survey3W_RGN', False),
                                    (37386, '2I', 1, (337, 100), False), (41989, 'H', 1, 19, False)])
        positions[name] = position
        record['odm_image'] = name
        record['status'] = 'prepared'
        records.append(record)
        print(f'Prepare RAW {number}/{len(raws)}: {path.name}', flush=True)
    report = {'raw_count': len(raws), 'prepared_count': len(records), 'rejected_count': len(rejected),
              'records': records, 'rejected': rejected, 'scale': scale,
              'units': 'relative_signal', 'settings': settings,
              'analysis_eligibility': {'absolute_reflectance': False, 'cross_survey_comparison': False},
              'capture_days': sorted(capture_days),
              'capture_day_consistency': 'verified_single_day' if records and all(record['capture_day'] is not None for record in records) else 'unverified',
              'warnings': [] if records and all(record['capture_day'] is not None for record in records) else ['Capture day is missing for some usable images; survey/flight consistency needs verification from Group A'],
              'position_source': 'paired JPG EXIF GPS; no positions invented'}
    (output_dir / 'preprocessing.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    minimum = config.get('mosaicking', {}).get('min_images', 3)
    if len(records) < minimum:
        raise ValueError(f'Only {len(records)} usable geotagged RAW images; ODM needs at least {minimum}. See preprocessing report.')
    return {'image_dir': image_dir, 'positions': positions, 'report': report}
