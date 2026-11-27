"""Validated, packaged defaults for the end-to-end workflow."""

from copy import deepcopy
from importlib.resources import files
import math
from pathlib import Path
import re
import yaml


def load_workflow_config(path: Path | None = None) -> dict:
    defaults = yaml.safe_load(files('agriscan').joinpath('configs/workflow.yaml').read_text(encoding='utf-8'))
    if path is None:
        config = defaults
    else:
        try:
            supplied = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
        except yaml.YAMLError as exc:
            raise ValueError(f'Invalid workflow YAML: {exc}') from exc
        if not isinstance(supplied, dict):
            raise ValueError('Workflow config must be a YAML object')
        def merge(base, override):
            result = deepcopy(base)
            for key, value in override.items():
                if key not in base:
                    raise ValueError(f'Unknown workflow setting: {key}')
                if isinstance(base[key], dict):
                    if not isinstance(value, dict):
                        raise ValueError(f'{key} must be a mapping')
                    result[key] = merge(base[key], value)
                else:
                    result[key] = value
            return result
        config = merge(defaults, supplied)
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Workflow schema_version must be 1')
    if config['camera'] != {'model': 'Survey3W', 'filter': 'RGN'}:
        raise ValueError('This workflow supports Survey3W RGN; never mix filters')
    if config['radiometry']['mode'] != 'relative' or type(config['radiometry']['allow_experimental']) is not bool:
        raise ValueError('radiometry requires mode: relative and boolean allow_experimental')
    def number(section, key, *, minimum=None, maximum=None, integer=False):
        value = config[section][key]
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f'{section}.{key} must be a finite number')
        if integer and value != int(value):
            raise ValueError(f'{section}.{key} must be an integer')
        if minimum is not None and value < minimum or maximum is not None and value > maximum:
            raise ValueError(f'{section}.{key} must lie in [{minimum}, {maximum}]')
        return value

    odm = config['mosaicking']
    number('mosaicking', 'max_concurrency', minimum=1, maximum=64, integer=True)
    number('mosaicking', 'memory_gb', minimum=2, maximum=2048)
    number('mosaicking', 'timeout_seconds', minimum=1, maximum=172800)
    number('mosaicking', 'min_images', minimum=3, integer=True)
    number('mosaicking', 'common_scale', minimum=1, maximum=65535)
    number('mosaicking', 'min_used_ratio', minimum=0.9, maximum=1)
    number('mosaicking', 'max_retries', minimum=0, maximum=2, integer=True)
    number('mosaicking', 'orthophoto_resolution', minimum=0.1, maximum=1000)
    if not isinstance(odm['image'], str) or not re.fullmatch(r'opendronemap/odm:[A-Za-z0-9][A-Za-z0-9_.-]*', odm['image']) or odm['image'].endswith(':latest'):
        raise ValueError('Use a versioned official opendronemap/odm image')
    for key in ('feature_quality', 'pc_quality'):
        if odm[key] not in ('ultra', 'high', 'medium', 'low', 'lowest'):
            raise ValueError(f'mosaicking.{key} must be ultra/high/medium/low/lowest')
    red = number('indices', 'red_band', minimum=1, maximum=3, integer=True)
    nir = number('indices', 'nir_band', minimum=1, maximum=3, integer=True)
    if red == nir:
        raise ValueError('indices.red_band and nir_band must be different')
    number('indices', 'vegetation_threshold', minimum=-1, maximum=1)
    number('indices', 'brightness_min', minimum=0)
    if number('indices', 'reflectance_scale') <= 0:
        raise ValueError('indices.reflectance_scale must be positive')
    if number('grid', 'cell_size_m') <= 0:
        raise ValueError('grid.cell_size_m must be positive')
    number('grid', 'max_cells', minimum=1, integer=True)
    number('anomaly', 'absolute_threshold', minimum=-1, maximum=1)
    if number('anomaly', 'spatial_z_threshold') >= 0:
        raise ValueError('anomaly.spatial_z_threshold must be negative')
    number('anomaly', 'min_valid_pixels', minimum=1, integer=True)
    number('anomaly', 'min_vegetation_fraction', minimum=0, maximum=1)
    number('anomaly', 'min_coverage_fraction', minimum=0, maximum=1)
    number('anomaly', 'min_spatial_units', minimum=3, integer=True)
    if type(config['anomaly']['merge_adjacent']) is not bool:
        raise ValueError('anomaly.merge_adjacent must be true or false')
    ranking = config['anomaly']['ranking']
    weights = ranking.get('weights', ranking)
    for key, value in weights.items():
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError(f'anomaly.ranking.{key} must be finite and nonnegative')
    if sum(weights.values()) <= 0:
        raise ValueError('At least one anomaly ranking weight must be positive')
    return config
