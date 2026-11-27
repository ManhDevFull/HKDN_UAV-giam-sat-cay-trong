"""GeoTIFF I/O that preserves band registration and real georeferencing."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np
import rasterio


def assert_same_grid(*sources: Any) -> None:
    """Reject dimensions, CRS or pixel transforms that do not match exactly."""
    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(s)) if isinstance(s, (str, Path)) else s for s in sources]
        if not datasets:
            return
        reference = datasets[0]
        if reference.crs is None:
            raise ValueError("Registered raster comparison requires a CRS")
        for dataset in datasets[1:]:
            if (
                dataset.width != reference.width
                or dataset.height != reference.height
                or dataset.crs != reference.crs
                or dataset.transform != reference.transform
            ):
                raise ValueError("Red/NIR rasters must have the same CRS, transform, width and height")


def read_band(path: str | Path, band: int = 1, *, window: Any = None) -> tuple[np.ma.MaskedArray, dict]:
    """Read a nodata-aware band together with its source profile."""
    with rasterio.open(path) as dataset:
        if not 1 <= band <= dataset.count:
            raise ValueError(f"Band {band} is absent from {path}")
        values = dataset.read(band, window=window, masked=True)
        profile = dataset.profile.copy()
        if window is not None:
            profile.update(transform=dataset.window_transform(window), width=values.shape[1], height=values.shape[0])
        return values, profile


def read_registered_bands(
    red_path: str | Path,
    nir_path: str | Path,
    *,
    red_band: int = 1,
    nir_band: int = 1,
    window: Any = None,
) -> tuple[np.ma.MaskedArray, np.ma.MaskedArray, dict]:
    with rasterio.open(red_path) as red, rasterio.open(nir_path) as nir:
        assert_same_grid(red, nir)
        if not 1 <= red_band <= red.count or not 1 <= nir_band <= nir.count:
            raise ValueError("Requested Red/NIR band is absent")
        red_values = red.read(red_band, window=window, masked=True)
        nir_values = nir.read(nir_band, window=window, masked=True)
        profile = red.profile.copy()
        if window is not None:
            profile.update(transform=red.window_transform(window), width=red_values.shape[1], height=red_values.shape[0])
        return red_values, nir_values, profile


def output_profile(source: Any, *, dtype: str, count: int = 1, nodata: Any = None) -> dict:
    profile = source.profile.copy() if hasattr(source, "profile") else dict(source)
    profile.update(driver="GTiff", dtype=dtype, count=count, nodata=nodata, compress="deflate", BIGTIFF="IF_SAFER")
    # Strip JPEG/RGB-specific creation options inherited from an orthomosaic.
    for option in ("photometric", "interleave", "blockxsize", "blockysize"):
        profile.pop(option, None)
    profile.update(tiled=True, blockxsize=256, blockysize=256)
    return profile


def write_geotiff(
    path: str | Path,
    data: np.ndarray,
    profile: dict,
    *,
    nodata: Any = None,
    descriptions: list[str] | None = None,
    tags: dict | None = None,
) -> Path:
    array = np.asarray(data)
    if array.ndim == 2:
        array = array[None, :, :]
    if array.ndim != 3:
        raise ValueError("GeoTIFF array must be (height, width) or (bands, height, width)")
    if not profile.get("crs"):
        raise ValueError("A real CRS is required for map output")
    if profile.get("transform") is None:
        raise ValueError("A real pixel transform is required for map output")
    if descriptions and len(descriptions) != array.shape[0]:
        raise ValueError("Each raster band needs a description")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    target_profile = output_profile(profile, dtype=str(array.dtype), count=array.shape[0], nodata=nodata)
    target_profile.update(height=array.shape[1], width=array.shape[2])
    with rasterio.open(path, "w", **target_profile) as dataset:
        dataset.write(array)
        if descriptions:
            dataset.descriptions = tuple(descriptions)
        if tags:
            dataset.update_tags(**tags)
    return path
