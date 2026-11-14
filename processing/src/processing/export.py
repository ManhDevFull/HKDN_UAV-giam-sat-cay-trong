"""Lossless raster handoff from preprocessing to the platform team."""

import json
from pathlib import Path

import numpy as np
import tifffile


def save_multiband(output_dir: Path, planes: dict[str, np.ndarray], metadata: dict,
                   filter_name: str = 'RGN') -> dict:
    """Write three nominal bands and an independent, all-band validity mask.

    TIFF pixel coordinates have no map reference. RGN cameras expose the
    nominal NIR signal through the Bayer B plane; no spectral unmixing is
    implied by the exported band names.
    """
    if filter_name not in ('RGN', 'RGB'):
        raise ValueError('Raster filter must be RGN or RGB')
    if not isinstance(planes, dict) or set(planes) != {'R', 'G1', 'G2', 'B'}:
        raise ValueError('Raster planes must contain exactly R, G1, G2 and B')
    converted = {}
    shape = None
    for name in ('R', 'G1', 'G2', 'B'):
        plane = np.asarray(planes[name])
        if (plane.ndim != 2 or not all(plane.shape) or
                not np.issubdtype(plane.dtype, np.number) or np.iscomplexobj(plane)):
            raise ValueError('Raster planes must be nonempty two-dimensional real numeric arrays')
        if shape is not None and plane.shape != shape:
            raise ValueError('Raster planes must have the same shape')
        shape = plane.shape
        if np.any(np.isinf(plane)):
            raise ValueError('Raster planes may contain NaN nodata, but not infinity')
        with np.errstate(over='ignore', invalid='ignore'):
            converted[name] = plane.astype(np.float32, copy=True)
        if np.any(np.isinf(converted[name])):
            raise ValueError('Raster values must fit in float32')
    units = metadata.get('units')
    if not isinstance(units, str) or not units:
        raise ValueError('Raster metadata must declare nonempty units')
    bands = ['red', 'green', 'nir' if filter_name == 'RGN' else 'blue']
    description = {
        'schema_version': 1,
        'bands': bands,
        'units': units,
        'correction_status': metadata.get('correction_status', metadata.get('status', 'unknown')),
        'source': metadata.get('source'),
        'georeferenced': False,
        'nodata': 'NaN',
    }
    # TIFF ImageDescription is ASCII; JSON escaping preserves Unicode paths.
    description_json = json.dumps(description, ensure_ascii=True, allow_nan=False)
    # Halving before adding avoids overflowing a representable green average.
    green = converted['G1'] * np.float32(0.5) + converted['G2'] * np.float32(0.5)
    raster = np.stack((converted['R'], green, converted['B']), axis=-1)
    valid = np.logical_and.reduce([np.isfinite(plane) for plane in converted.values()]).astype(np.uint8)
    output_dir = Path(output_dir)
    raster_path = output_dir / 'bands.tif'
    mask_path = output_dir / 'valid_mask.tif'
    # Check both destinations before writing either file. Exclusive creation
    # also protects existing data if another process creates a file meanwhile.
    if raster_path.exists() or mask_path.exists():
        raise FileExistsError('Raster output already exists; choose a new output directory')
    output_dir.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        with raster_path.open('xb') as stream:
            created.append(raster_path)
            tifffile.imwrite(stream, raster, photometric='minisblack', planarconfig='contig',
                             extrasamples=('unspecified', 'unspecified'), metadata=None,
                             description=description_json)
        with mask_path.open('xb') as stream:
            created.append(mask_path)
            tifffile.imwrite(stream, valid, photometric='minisblack', metadata=None,
                             description=json.dumps({'schema_version': 1,
                                                     'valid_values': {'0': 'invalid', '1': 'valid'},
                                                     'georeferenced': False}))
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {'raster': raster_path.name, 'valid_mask': mask_path.name, 'bands': bands,
            'units': units, 'georeferenced': False, 'nodata': 'NaN'}
