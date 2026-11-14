"""Flat-field vignetting correction for channel planes."""

import numpy as np


def correct_vignetting(image: np.ndarray, flat: np.ndarray, *, epsilon: float = 1e-6) -> np.ndarray:
    """Correct an image using a same-channel flat field, preserving image scale.

    The flat is normalized by its median. This simple implementation is intended
    for controlled synthetic and calibration data; real work needs dark-level,
    exposure, saturation, and calibration-frame checks.
    """
    if image.shape != flat.shape:
        raise ValueError("image and flat must have identical shapes")
    image_f = image.astype(np.float32)
    flat_f = flat.astype(np.float32)
    positive = flat_f[flat_f > epsilon]
    if positive.size == 0:
        raise ValueError("flat field has no positive values")
    normalized = flat_f / np.median(positive)
    return image_f / np.maximum(normalized, epsilon)


def radial_flat(shape: tuple[int, int], strength: float = 0.35) -> np.ndarray:
    """Create a smooth synthetic radial shading field in [1-strength, 1]."""
    height, width = shape
    y, x = np.mgrid[-1:1:complex(height), -1:1:complex(width)]
    radius2 = x * x + y * y
    return np.clip(1.0 - strength * radius2, 1.0 - strength, 1.0).astype(np.float32)
