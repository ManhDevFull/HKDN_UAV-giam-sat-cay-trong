"""NDVI on registered linear Red/NIR samples; invalid input stays nodata."""

from __future__ import annotations

import numpy as np

NDVI_NODATA = -9999.0


def calculate_ndvi(
    red: np.ndarray,
    nir: np.ndarray,
    *,
    valid_mask: np.ndarray | None = None,
    nodata: float = NDVI_NODATA,
    epsilon: float = 1e-12,
) -> np.ndarray:
    """Compute (NIR - Red)/(NIR + Red) without interpreting dark/invalid pixels.

    Inputs must already share their geometry, scale and radiometric correction.
    A negative reflectance, masked value, non-finite sample or zero denominator
    is invalid, rather than a plausible NDVI of zero.
    """
    red_values = np.asarray(np.ma.filled(np.ma.asarray(red, dtype=np.float32), np.nan))
    nir_values = np.asarray(np.ma.filled(np.ma.asarray(nir, dtype=np.float32), np.nan))
    if red_values.shape != nir_values.shape:
        raise ValueError("Red and NIR must have the same shape and registered geometry")
    if epsilon < 0 or not np.isfinite(epsilon):
        raise ValueError("epsilon must be finite and non-negative")
    # Accumulate in float64 so valid large integer/float signals cannot overflow
    # the denominator and silently produce a false NDVI of zero.
    denominator = np.add(red_values, nir_values, dtype=np.float64)
    valid = (
        np.isfinite(red_values)
        & np.isfinite(nir_values)
        & (red_values >= 0)
        & (nir_values >= 0)
        & (denominator > epsilon)
    )
    if valid_mask is not None:
        if np.shape(valid_mask) != valid.shape:
            raise ValueError("valid_mask must have the same shape as Red/NIR")
        valid &= np.asarray(valid_mask, dtype=bool)
    result = np.full(red_values.shape, nodata, dtype=np.float32)
    np.divide(np.subtract(nir_values, red_values, dtype=np.float64), denominator, out=result, where=valid)
    # Only absorb floating point rounding; invalid inputs never get clipped in.
    result[valid] = np.clip(result[valid], -1.0, 1.0)
    return result


compute_ndvi = calculate_ndvi
