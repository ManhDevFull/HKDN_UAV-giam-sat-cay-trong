"""Explicit vegetation, bare-soil and shadow exclusions for linear signals."""

from __future__ import annotations

import numpy as np

from agriscan.indices.ndvi import NDVI_NODATA

MASK_NODATA = 255


def build_masks(
    red: np.ndarray,
    nir: np.ndarray,
    ndvi: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
    vegetation_threshold: float = 0.2,
    brightness_min: float = 0.03,
    reflectance_scale: float = 1.0,
) -> dict[str, np.ndarray]:
    """Keep weak vegetation above threshold; reject low Red+NIR signal.

    brightness_min is a fixed threshold for (Red + NIR)/reflectance_scale.
    It is never adapted from each image's histogram. These configurable masks
    are screening heuristics, not a ground-truth land-cover classification.
    """
    red = np.asarray(np.ma.filled(np.ma.asarray(red, dtype=np.float32), np.nan))
    nir = np.asarray(np.ma.filled(np.ma.asarray(nir, dtype=np.float32), np.nan))
    ndvi = np.asarray(ndvi)
    if red.shape != nir.shape or red.shape != ndvi.shape:
        raise ValueError("Red, NIR and NDVI must share a shape")
    if not -1 <= vegetation_threshold <= 1:
        raise ValueError("vegetation_threshold must lie in [-1, 1]")
    if not np.isfinite(reflectance_scale) or reflectance_scale <= 0:
        raise ValueError("reflectance_scale must be positive and finite")
    if not np.isfinite(brightness_min) or brightness_min < 0:
        raise ValueError("brightness_min must be finite and non-negative")
    valid = (
        np.isfinite(ndvi)
        & (ndvi != NDVI_NODATA)
        & (ndvi >= -1)
        & (ndvi <= 1)
        & np.isfinite(red)
        & np.isfinite(nir)
        & (red >= 0)
        & (nir >= 0)
        & ((red + nir) > 0)
    )
    if valid_mask is not None:
        if np.shape(valid_mask) != valid.shape:
            raise ValueError("valid_mask must have the same shape as the bands")
        valid &= np.asarray(valid_mask, dtype=bool)
    shadow = valid & (((red + nir) / reflectance_scale) < brightness_min)
    bare_soil = valid & ~shadow & (ndvi <= vegetation_threshold)
    vegetation = valid & ~shadow & ~bare_soil
    return {"valid": valid, "vegetation": vegetation, "shadow": shadow, "bare_soil": bare_soil}


def as_mask_raster(mask: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Encode 0/1 with 255 reserved for nodata."""
    result = np.full(np.shape(mask), MASK_NODATA, dtype=np.uint8)
    result[valid] = np.asarray(mask, dtype=np.uint8)[valid]
    return result
