"""Transactional RAW → ODM → vegetation maps → ranked screening alerts."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import version
import json
from pathlib import Path
import shutil

import numpy as np
import rasterio

from agriscan.anomalies.ranking import generate_alerts
from agriscan.calibration.preprocess import prepare_images
from agriscan.indices.statistics import analyze_mosaic
from agriscan.io.image_validator import validate_survey_folder
from agriscan.io.metadata_reader import read_metadata
from agriscan.mosaicking.mosaic_quality import inspect_mosaic
from agriscan.mosaicking.odm_runner import run_odm
from agriscan.pipeline.storage import transaction
from agriscan.pipeline.workflow_config import load_workflow_config


class WorkflowError(RuntimeError):
    """A failed run with a useful report and no replacement of the prior output."""


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def default_output(source: Path) -> Path:
    """One stable output, whether invoked from repo root or processing/."""
    return Path(__file__).resolve().parents[3] / 'output' / source.resolve().stem


def _relative_paths(value, stage: Path):
    if isinstance(value, dict):
        return {key: _relative_paths(item, stage) for key, item in value.items()}
    if isinstance(value, list):
        return [_relative_paths(item, stage) for item in value]
    if isinstance(value, str) and value.startswith(str(stage) + '/'):
        return Path(value).relative_to(stage).as_posix()
    return value


def _finalize_json(stage: Path) -> None:
    for path in stage.rglob('*.json'):
        _write_json(path, _relative_paths(json.loads(path.read_text(encoding='utf-8')), stage))


def _normalize_mosaic(source_path: Path, output_path: Path, scale: float) -> None:
    """Undo the shared TIFF encoding scale; never stretch individual images."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(source_path) as source:
        profile = source.profile.copy()
        profile.update(count=3, dtype='float32', nodata=-9999.0, compress='deflate', predictor=3,
                       tiled=True, blockxsize=256, blockysize=256, BIGTIFF='IF_SAFER')
        profile.pop('photometric', None)
        with rasterio.open(output_path, 'w', **profile) as target:
            for _, window in source.block_windows(1):
                values = source.read((1, 2, 3), window=window).astype('float32') / scale
                valid = np.all(source.read_masks((1, 2, 3), window=window) > 0, axis=0)
                valid &= np.all(np.isfinite(values), axis=0)
                values[:, ~valid] = -9999.0
                target.write(values, window=window)
            for i, name in enumerate(('red', 'green', 'nir'), 1):
                target.set_band_description(i, name)
            target.update_tags(units='relative_signal', radiometry='experimental',
                               band_order='red,green,nir', cross_survey_comparison='false')


def _analyze(stage: Path, mosaic: Path, config: dict, survey_id: str, plot_id: str,
             *, boundary_path: Path | None, source_info: dict, quality: dict, synthetic=False) -> dict:
    print('NDVI, masks and metric grid...', flush=True)
    indices = analyze_mosaic(mosaic, stage / 'maps', config=config, survey_id=survey_id,
                             plot_id=plot_id, boundary_path=boundary_path)
    print('Methods A/B and alert priorities...', flush=True)
    alerts = generate_alerts(indices['records'], survey_id=survey_id, plot_id=plot_id,
                             config=config, output_dir=stage / 'alerts', crs=indices['crs'])
    paths = {'orthomosaic': str(mosaic), **indices['paths'], **alerts['paths']}
    eligibility = {'experimental': True, 'synthetic': synthetic, 'absolute_reflectance': False,
                   'absolute_reflectance_accuracy_lt_5_percent': 'not_verified',
                   'cross_survey_comparison': False, 'disease_diagnosis': False,
                   'purpose': 'Within-survey vegetation screening; thresholds need field validation'}
    report = {'schema_version': 1, 'status': 'completed', 'survey_id': survey_id, 'plot_id': plot_id,
              'created_at': datetime.now(timezone.utc).isoformat(), 'software_version': version('survey-processing'),
              'source': source_info, 'analysis_eligibility': eligibility, 'mosaic_quality': quality,
              'crs_metadata': indices['crs_metadata'], 'grid_unit_count': len(indices['records']),
              'pixel_counts': indices['summary'],
              'anomalies': {k: alerts[k] for k in ('eligible_unit_count', 'excluded_unit_count', 'method_a_count',
                                                  'method_b_count', 'alert_count', 'counts_by_severity')},
              'methods': {'A': 'NDVI below configured threshold', 'B': 'Lower-tail z-score across eligible cells in the same plot'},
              'paths': paths}
    manifest = {'schema_version': 1, 'stage': 'vegetation_screening', 'survey_id': survey_id, 'plot_id': plot_id,
                'analysis_eligibility': eligibility, 'band_order': ['red', 'green', 'nir'], 'units': 'relative_signal',
                'geojson_crs': 'EPSG:4326', 'raster_crs': indices['crs'], 'paths': paths,
                'summary': 'summary.json', 'config': 'workflow.yaml',
                'backend_import': 'Map survey_id/plot_id/unit_id codes to backend UUIDs before import'}
    import yaml
    (stage / 'workflow.yaml').write_text(yaml.safe_dump(config, sort_keys=False), encoding='utf-8')
    _write_json(stage / 'manifest.json', manifest)
    _write_json(stage / 'summary.json', report)
    _finalize_json(stage)
    return _relative_paths(report, stage)


def _failure(target: Path, exc: Exception, phase: str, diagnostics: dict) -> Path | None:
    """One owned failure report beside the successful output; no growing run folders."""
    failure = target.parent / f'{target.name}.failure.json'
    if failure.is_symlink():
        return
    if failure.exists():
        try:
            existing = json.loads(failure.read_text())
            if not isinstance(existing, dict) or existing.get('tool') != 'agriscan-workflow':
                return
        except (OSError, ValueError):
            return
    try:
        _write_json(failure, {'tool': 'agriscan-workflow', 'status': 'failed', 'phase': phase,
                             'code': getattr(exc, 'code', type(exc).__name__), 'error': str(exc),
                             'previous_output_preserved': True, **diagnostics})
        return failure
    except OSError:
        return None


def _clear_failure(target: Path) -> None:
    failure = target.parent / f'{target.name}.failure.json'
    if failure.is_file() and not failure.is_symlink():
        try:
            existing = json.loads(failure.read_text())
            if isinstance(existing, dict) and existing.get('tool') == 'agriscan-workflow':
                failure.unlink()
        except (OSError, ValueError):
            pass


def run_pipeline(config_path: str | Path | None = None, survey_dir: str | Path | None = None,
                 *, output_dir: str | Path | None = None, experimental: bool = False,
                 boundary_path: str | Path | None = None) -> dict:
    """Run a complete Group A folder, keeping previous output until all gates pass."""
    config = load_workflow_config(Path(config_path) if config_path else None)
    source = Path(survey_dir or 'assets').resolve()
    target = Path(output_dir).absolute() if output_dir else default_output(source)
    boundary = Path(boundary_path).resolve() if boundary_path else None
    if not (experimental or config['radiometry']['allow_experimental']):
        raise WorkflowError('Chưa có hiệu chuẩn phản xạ được kiểm chứng. Dùng --experimental để sàng lọc NDVI tương đối; không so sánh khác buổi.')
    phase, diagnostics, entered = 'validation', {}, False
    try:
        with transaction(source, target) as stage:
            entered = True
            # Capture transient ODM logs before the transaction removes scratch.
            try:
                validation = validate_survey_folder(source)
                diagnostics['validation'] = validation
                _write_json(stage / 'validation.json', validation)
                if not validation['is_valid']:
                    raise WorkflowError('Đầu vào không hợp lệ: ' + '; '.join(validation['errors']))
                metadata = read_metadata(source)
                phase = 'preprocessing'
                prepared = prepare_images(source, stage.parent / 'prepared', metadata, config)
                diagnostics['preprocessing'] = prepared['report']
                _write_json(stage / 'preprocessing.json', prepared['report'])
                phase = 'odm'
                print(f"ODM: {prepared['report']['prepared_count']} usable RAW images; this can take several minutes...", flush=True)
                encoded = stage / 'maps' / 'orthomosaic_dn.tif'
                odm = run_odm(prepared['image_dir'], stage.parent / 'odm', encoded,
                              config=config['mosaicking'], positions=prepared['positions'], boundary_path=boundary)
                logs = stage / 'logs'
                logs.mkdir()
                for attempt in odm['attempts']:
                    source_log = Path(attempt['log'])
                    shutil.copyfile(source_log, logs / source_log.name)
                    attempt['log'] = str(logs / source_log.name)
                odm['log_path'] = odm['attempts'][-1]['log']
                odm.pop('native_orthomosaic', None)
                odm.pop('quality_path', None)
                phase = 'analysis'
                mosaic = stage / 'maps' / 'orthomosaic.tif'
                _normalize_mosaic(encoded, mosaic, config['mosaicking']['common_scale'])
                encoded.unlink()
                odm['orthomosaic'], odm['quality']['path'] = str(mosaic), str(mosaic)
                odm['quality']['assessed_encoding'] = 'ODM uint16 before shared-scale decoding'
                odm['canonical_encoding'] = {'dtype': 'float32', 'units': 'relative_signal',
                                              'decoded_scale': config['mosaicking']['common_scale']}
                _write_json(stage / 'mosaic_quality.json', odm)
                report = _analyze(stage, mosaic, config, str(metadata['survey_id']), str(metadata['plot_id']),
                                  boundary_path=boundary, quality=odm,
                                  source_info={'type': 'raw', 'counts': validation['counts'],
                                               'prepared_images': prepared['report']['prepared_count'],
                                               'rejected_images': prepared['report']['rejected_count']})
            except Exception as exc:
                log_path = getattr(exc, 'log_path', None)
                if log_path and Path(log_path).is_file():
                    with Path(log_path).open('rb') as log:
                        log.seek(max(0, Path(log_path).stat().st_size - 30000))
                        diagnostics['odm_log_tail'] = log.read().decode('utf-8', errors='replace')
                preprocessing = stage.parent / 'prepared' / 'preprocessing.json'
                if preprocessing.is_file() and 'preprocessing' not in diagnostics:
                    diagnostics['preprocessing'] = json.loads(preprocessing.read_text())
                raise
    except Exception as exc:
        failure = _failure(target, exc, phase, diagnostics) if entered else None
        raise WorkflowError(str(exc) + (f' Report: {failure}' if failure else '')) from exc
    _clear_failure(target)
    print(f"Completed: {report['grid_unit_count']} cells, {report['anomalies']['alert_count']} alerts. {target / 'manifest.json'}", flush=True)
    return report


def analyze_existing(mosaic_path: Path, *, survey_id: str, plot_id: str, output_dir: Path | None = None,
                     config_path: Path | None = None, experimental: bool = False,
                     boundary_path: Path | None = None) -> dict:
    """Analyze an existing linear R/G/NIR float32 mosaic in relative signal units."""
    config = load_workflow_config(config_path)
    if not (experimental or config['radiometry']['allow_experimental']):
        raise WorkflowError('Use --experimental for relative-signal NDVI screening')
    source = mosaic_path.resolve()
    target = output_dir.absolute() if output_dir else default_output(source)
    entered = False
    try:
        with transaction(source, target) as stage:
            entered = True
            quality = inspect_mosaic(source, boundary_path=boundary_path)
            with rasterio.open(source) as image:
                if image.count != 3 or any(dtype != 'float32' for dtype in image.dtypes):
                    raise WorkflowError('analyze requires 3-band float32 linear relative-signal R/G/NIR; convert DN using its known common scale first')
                tags = image.tags()
                if tags.get('units') != 'relative_signal' or tags.get('band_order') != 'red,green,nir':
                    raise WorkflowError('Input needs verified units=relative_signal and band_order=red,green,nir tags; never relabel RGB/JPG')
                synthetic = tags.get('synthetic', '').lower() == 'true'
            destination = stage / 'maps' / 'orthomosaic.tif'
            destination.parent.mkdir()
            from rasterio.shutil import copy as copy_raster
            with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True):
                copy_raster(source, destination, driver='GTiff')
            quality['path'] = str(destination)
            report = _analyze(stage, destination, config, survey_id, plot_id, boundary_path=boundary_path,
                              quality=quality, source_info={'type': 'existing_mosaic', 'odm_reconstruction_verified': False},
                              synthetic=synthetic)
    except Exception as exc:
        failure = _failure(target, exc, 'analysis', {}) if entered else None
        raise WorkflowError(str(exc) + (f' Report: {failure}' if failure else '')) from exc
    _clear_failure(target)
    print(f"Completed: {target / 'manifest.json'}", flush=True)
    return report


def run_demo(*, output_dir: Path | None = None, config_path: Path | None = None) -> dict:
    """Exercise real GIS calculations on deterministic synthetic bands, without ODM."""
    from agriscan.pipeline.demo import create_demo_mosaic
    config = load_workflow_config(config_path)
    target = output_dir.absolute() if output_dir else default_output(Path('demo'))
    identity = default_output(Path('demo')).parent.parent / 'data' / 'demo-source'
    entered = False
    try:
        with transaction(identity, target) as stage:
            entered = True
            mosaic = stage / 'maps' / 'orthomosaic.tif'
            create_demo_mosaic(mosaic)
            quality = inspect_mosaic(mosaic)
            report = _analyze(stage, mosaic, config, 'demo-survey', 'demo-plot', boundary_path=None,
                              quality=quality, source_info={'type': 'synthetic', 'odm_executed': False}, synthetic=True)
    except Exception as exc:
        failure = _failure(target, exc, 'demo', {}) if entered else None
        raise WorkflowError(str(exc) + (f' Report: {failure}' if failure else '')) from exc
    _clear_failure(target)
    print(f"Synthetic demo completed (no ODM): {target / 'manifest.json'}", flush=True)
    return report
