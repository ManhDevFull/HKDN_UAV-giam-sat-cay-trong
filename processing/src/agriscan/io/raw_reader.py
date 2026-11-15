"""Step 1 — Read RAW sensor mosaic and attach verified camera/band metadata."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from agriscan.calibration.decoder import (
    MAPIR_DEFAULT_HEIGHT,
    MAPIR_DEFAULT_WIDTH,
    decode_raw_file,
)


def read_raw(
    file_path: str | Path,
    *,
    survey_metadata: dict[str, Any] | None = None,
    width: int = MAPIR_DEFAULT_WIDTH,
    height: int = MAPIR_DEFAULT_HEIGHT,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Read a RAW file using a verified decoder and return (mosaic, metadata).

    Performs:
        1. File existence and non-empty check.
        2. Format identification and decoding (MAPIR 12-bit packed RAW, .npy, or rawpy).
        3. Dimension, bit-depth, and CFA channel structure verification.
        4. Pixel sanity checks (min, max, mean, zero count, saturation count).
        5. Attaches confirmed camera/filter/band mapping when survey_metadata is provided.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"RAW file does not exist: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"RAW file is empty (0 bytes): {path}")

    mosaic, meta = decode_raw_file(path, width=width, height=height)

    if mosaic.ndim != 2 or mosaic.shape[0] % 2 != 0 or mosaic.shape[1] % 2 != 0:
        raise ValueError(f"Decoded mosaic must be 2D with even dimensions, got {mosaic.shape}")

    white_level = int(meta.get("white_level", 4095))
    total_pixels = int(mosaic.size)
    zero_pixels = int(np.count_nonzero(mosaic == 0))
    saturated_pixels = int(np.count_nonzero(mosaic >= white_level))

    meta["pixel_stats"] = {
        "min": int(mosaic.min()),
        "max": int(mosaic.max()),
        "mean": round(float(mosaic.mean()), 2),
        "std": round(float(mosaic.std()), 2),
        "total_pixels": total_pixels,
        "zero_pixels": zero_pixels,
        "saturated_pixels": saturated_pixels,
        "saturated_ratio": round(saturated_pixels / total_pixels, 6),
    }

    if survey_metadata and isinstance(survey_metadata.get("camera"), dict):
        cam = survey_metadata["camera"]
        meta["camera"] = {
            "model": cam.get("model"),
            "filter": cam.get("filter"),
            "bands": cam.get("bands"),
            "band_confirmation_status": "confirmed" if cam.get("filter") else "unconfirmed",
        }
    else:
        meta["camera"] = {
            "model": "MAPIR Survey3W",
            "filter": "RGN",
            "bands": {"red": 660, "green": 550, "nir": 850},
            "band_confirmation_status": "default_camera_config",
        }

    return mosaic, meta
