"""Confirmed RAW decoders for MAPIR Survey3W 12-bit packed RAW and standard RAW formats."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import numpy as np

DECODER_VERSION = "1.0.0"
MAPIR_DEFAULT_WIDTH = 4000
MAPIR_DEFAULT_HEIGHT = 3000
MAPIR_BIT_DEPTH = 12
MAPIR_WHITE_LEVEL = (1 << MAPIR_BIT_DEPTH) - 1  # 4095


def decode_mapir_raw12(
    file_path: str | Path,
    *,
    width: int = MAPIR_DEFAULT_WIDTH,
    height: int = MAPIR_DEFAULT_HEIGHT,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Decode a headerless MAPIR Survey3 12-bit little-endian packed RAW file.

    Every 3 bytes (b0, b1, b2) encode two consecutive 12-bit pixels (p0, p1):
        p0 = b0 | ((b1 & 0x0F) << 8)
        p1 = (b1 >> 4) | (b2 << 4)

    Args:
        file_path: Path to the .RAW file.
        width: Sensor image width in pixels (default: 4000).
        height: Sensor image height in pixels (default: 3000).

    Returns:
        Tuple of:
            - 2D numpy.ndarray of shape (height, width) and dtype uint16 (values in 0..4095)
            - Metadata dictionary describing the decoder, dimensions, and pixel range
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"RAW file not found: {path}")

    if width <= 0 or height <= 0 or (width % 2 != 0) or (height % 2 != 0):
        raise ValueError(f"Sensor width and height must be positive even integers, got {width}x{height}")

    expected_bytes = (width * height * 3) // 2
    actual_bytes = path.stat().st_size
    if actual_bytes != expected_bytes:
        raise ValueError(
            f"File size mismatch for MAPIR 12-bit packed RAW '{path.name}': "
            f"got {actual_bytes} bytes, expected {expected_bytes} bytes for {width}x{height}"
        )

    raw_bytes = np.fromfile(path, dtype=np.uint8).reshape(-1, 3).astype(np.uint16)
    b0 = raw_bytes[:, 0]
    b1 = raw_bytes[:, 1]
    b2 = raw_bytes[:, 2]

    p0 = b0 | ((b1 & 0x0F) << 8)
    p1 = (b1 >> 4) | (b2 << 4)

    mosaic = np.empty(width * height, dtype=np.uint16)
    mosaic[0::2] = p0
    mosaic[1::2] = p1
    mosaic = mosaic.reshape((height, width))

    metadata: dict[str, Any] = {
        "source": path.name,
        "decoder": "mapir_raw12_le",
        "decoder_version": DECODER_VERSION,
        "width": int(width),
        "height": int(height),
        "bit_depth": MAPIR_BIT_DEPTH,
        "dtype": str(mosaic.dtype),
        "white_level": MAPIR_WHITE_LEVEL,
        "black_level": 0,
        "cfa_pattern": "RGGB",
    }
    return mosaic, metadata


def decode_rawpy(file_path: str | Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Decode standard camera RAW formats (e.g. DNG, CR2, TIFF-based RAW) via rawpy."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"RAW file not found: {path}")

    try:
        rawpy = importlib.import_module("rawpy")
    except ImportError as exc:
        raise RuntimeError(
            "Standard RAW decoding requires 'rawpy'. Install with: pip install rawpy"
        ) from exc

    with rawpy.imread(str(path)) as raw:
        mosaic = raw.raw_image_visible.copy()
        metadata: dict[str, Any] = {
            "source": path.name,
            "decoder": "rawpy",
            "decoder_version": getattr(rawpy, "__version__", "unknown"),
            "width": int(mosaic.shape[1]),
            "height": int(mosaic.shape[0]),
            "dtype": str(mosaic.dtype),
            "cfa_pattern": raw.raw_pattern.tolist(),
            "color_desc": raw.color_desc.decode("ascii", errors="replace"),
            "black_level_per_channel": list(raw.black_level_per_channel),
            "white_level": int(raw.white_level),
        }
    return mosaic, metadata


def decode_raw_file(
    file_path: str | Path,
    *,
    width: int = MAPIR_DEFAULT_WIDTH,
    height: int = MAPIR_DEFAULT_HEIGHT,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Automatically detect and decode a MAPIR .RAW, synthetic .npy, or standard RAW file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".npy":
        mosaic = np.load(path)
        if mosaic.ndim != 2:
            raise ValueError(f"Expected 2D mosaic array in {path.name}, got shape {mosaic.shape}")
        metadata: dict[str, Any] = {
            "source": path.name,
            "decoder": "numpy_npy",
            "decoder_version": DECODER_VERSION,
            "width": int(mosaic.shape[1]),
            "height": int(mosaic.shape[0]),
            "bit_depth": 12 if mosaic.max() <= 4095 else 16,
            "dtype": str(mosaic.dtype),
            "white_level": 4095 if mosaic.max() <= 4095 else 65535,
            "black_level": 0,
            "cfa_pattern": "RGGB",
        }
        return mosaic, metadata

    expected_mapir_bytes = (width * height * 3) // 2
    if suffix == ".raw" and path.stat().st_size == expected_mapir_bytes:
        return decode_mapir_raw12(path, width=width, height=height)

    if suffix == ".raw":
        # If size does not match width*height*1.5, raise a clear error explaining why
        return decode_mapir_raw12(path, width=width, height=height)

    return decode_rawpy(path)
