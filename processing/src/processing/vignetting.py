"""Flat-field vignetting correction for channel planes."""

import numpy as np


def correct_vignetting(image: np.ndarray, flat: np.ndarray, *, epsilon: float = 1e-6) -> np.ndarray:
    """Correct an image using a same-channel flat field, preserving image scale.

    Both inputs must already have their black levels removed. A flat must be a
    uniformly illuminated, unsaturated calibration frame, never a scene image.
    """
    if image.ndim != 2 or image.shape != flat.shape or not image.size:
        raise ValueError("image and flat must be nonempty 2D arrays with identical shapes")
    image_f = image.astype(np.float32)
    flat_f = flat.astype(np.float32)
    if not np.isfinite(epsilon) or epsilon <= 0:
        raise ValueError("epsilon must be finite and positive")
    if not np.all(np.isfinite(flat_f)) or np.any(flat_f <= epsilon):
        raise ValueError("flat field must contain only finite, positive values")
    normalized = flat_f / np.median(flat_f)
    return image_f / normalized


def radial_flat(shape: tuple[int, int], strength: float = 0.35) -> np.ndarray:
    """Create a smooth synthetic radial shading field in [1-strength, 1]."""
    height, width = shape
    y, x = np.mgrid[-1:1:complex(height), -1:1:complex(width)]
    radius2 = x * x + y * y
    return np.clip(1.0 - strength * radius2, 1.0 - strength, 1.0).astype(np.float32)
