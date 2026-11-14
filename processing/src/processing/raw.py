"""RAW decoding adapters. Keep sensor values separate from rendered RGB.

Survey3 packing reference (MAPIR's own converter):
https://github.com/mapircamera/camera-scripts/blob/main/Convert_Survey3_RAW_To_Tiff/Convert_Survey3_RAW_to_Tiff.py
"""

from pathlib import Path

import numpy as np


_BAYER_PATTERNS = {"RGGB", "BGGR", "GRBG", "GBRG"}
_SURVEY3_WIDTH = 4000
_SURVEY3_HEIGHT = 3000
_SURVEY3_RAW_BYTES = _SURVEY3_WIDTH * _SURVEY3_HEIGHT * 3 // 2


def _unpack_survey3(data: np.ndarray) -> np.ndarray:
    """Unpack two 12-bit pixels per three bytes, without a uint16 gain."""
    if data.ndim != 1 or data.dtype != np.uint8 or data.size % 3:
        raise ValueError("Survey3 packed data must contain complete three-byte groups")
    groups = data.reshape(-1, 3).astype(np.uint16)
    pixels = np.empty(groups.shape[0] * 2, dtype=np.uint16)
    pixels[0::2] = groups[:, 0] | ((groups[:, 1] & 0x0F) << 8)
    pixels[1::2] = (groups[:, 1] >> 4) | (groups[:, 2] << 4)
    return pixels


def _decode_survey3(path: Path) -> tuple[np.ndarray, dict[str, object]]:
    data = np.fromfile(path, dtype=np.uint8)
    if data.size != _SURVEY3_RAW_BYTES:
        raise ValueError("Survey3 RAW must contain exactly 18,000,000 bytes (4000 x 3000 packed12)")
    mosaic = _unpack_survey3(data).reshape(_SURVEY3_HEIGHT, _SURVEY3_WIDTH)
    # MAPIR demosaics with BayerRG2RGB then writes through OpenCV's BGR API;
    # together these operations assign R to [0, 0] and B to [1, 1].
    metadata: dict[str, object] = {
        "source": path.name,
        "decoder": "mapir-survey3-packed12",
        "width": _SURVEY3_WIDTH,
        "height": _SURVEY3_HEIGHT,
        "pattern": "RGGB",
        "cfa_pattern": [[0, 1], [3, 2]],
        "color_desc": "RGBG",
        "bit_depth": 12,
        "black_levels": None,
        "black_level_per_channel": None,
        "white_level": 4095,
        "white_level_source": "12-bit encoding limit; sensor saturation has not been measured",
        "warnings": [
            "Headerless Survey3 layout identified by .RAW extension and 18,000,000-byte size; "
            "camera/filter identity must come from the capture metadata.",
            "Sensor black levels are not supplied by this headerless format.",
        ],
    }
    return mosaic, metadata


def decode_raw(path: Path) -> tuple[np.ndarray, dict[str, object]]:
    """Return a sensor mosaic, its visible Bayer pattern and decoding metadata.

    Headerless, 18 MB Survey3 .RAW files are decoded using NumPy. Other
    formats use optional rawpy/LibRaw. Values retain their native bit depth.
    This adapter does not apply black subtraction or spectral calibration.
    """
    path = Path(path)
    if path.suffix.lower() == ".raw" and path.stat().st_size == _SURVEY3_RAW_BYTES:
        return _decode_survey3(path)

    try:
        import rawpy
    except ImportError as exc:
        raise RuntimeError(
            "This RAW format needs the optional dependency: pip install -e '.[raw]'. "
            "Headerless Survey3 .RAW files must be exactly 18,000,000 bytes."
        ) from exc

    try:
        return _decode_rawpy(path, rawpy)
    except rawpy.LibRawError as exc:
        raise ValueError(f"{path.name}: cannot decode camera RAW ({exc})") from exc


def _decode_rawpy(path: Path, rawpy) -> tuple[np.ndarray, dict[str, object]]:
    """Read LibRaw data while allowing the public adapter to normalize errors."""
    with rawpy.imread(str(path)) as raw:
        mosaic = raw.raw_image_visible.copy()
        if raw.raw_pattern is None or raw.raw_pattern.shape != (2, 2):
            raise ValueError("RAW has no supported 2x2 RGB Bayer pattern")
        # Use visible positions, since a cropped margin can shift the CFA.
        cfa = raw.raw_colors_visible[:2, :2].copy()
        color_desc = raw.color_desc.decode("ascii", errors="replace").rstrip("\x00")
        if cfa.shape != (2, 2) or any(int(i) >= len(color_desc) for i in cfa.flat):
            raise ValueError("RAW has no supported 2x2 RGB Bayer pattern")
        pattern = "".join(color_desc[int(i)] for i in cfa.flat)
        if pattern not in _BAYER_PATTERNS:
            raise ValueError(f"Unsupported RGB Bayer pattern: {pattern!r}")
        levels = [int(value) for value in raw.black_level_per_channel]
        black_levels: dict[str, int] = {}
        green_index = 0
        for color_index, channel in zip(cfa.flat, pattern):
            if channel == "G":
                green_index += 1
                channel = f"G{green_index}"
            black_levels[channel] = levels[int(color_index)]
        metadata: dict[str, object] = {
            "source": path.name,
            "decoder": "rawpy",
            "width": int(mosaic.shape[1]),
            "height": int(mosaic.shape[0]),
            "pattern": pattern,
            "cfa_pattern": cfa.tolist(),
            "color_desc": color_desc,
            "black_levels": black_levels,
            "black_level_per_channel": levels,
            "white_level": int(raw.white_level),
            "white_level_source": "rawpy/LibRaw camera metadata",
            "warnings": [],
        }
    return mosaic, metadata


def split_bayer_channels(mosaic: np.ndarray, pattern: str = "RGGB") -> dict[str, np.ndarray]:
    """Split a 2x2 Bayer mosaic into named planes without demosaicing."""
    if mosaic.ndim != 2 or not mosaic.size or mosaic.shape[0] % 2 or mosaic.shape[1] % 2:
        raise ValueError("Expected a 2D mosaic with even width and height")
    pattern = pattern.upper()
    if pattern not in _BAYER_PATTERNS:
        raise ValueError("pattern must be one of RGGB, BGGR, GRBG or GBRG")
    positions = ((slice(0, None, 2), slice(0, None, 2)),
                 (slice(0, None, 2), slice(1, None, 2)),
                 (slice(1, None, 2), slice(0, None, 2)),
                 (slice(1, None, 2), slice(1, None, 2)))
    planes: dict[str, list[np.ndarray]] = {"R": [], "G": [], "B": []}
    for channel, slices in zip(pattern, positions):
        planes[channel].append(mosaic[slices])
    # Preserve both green sampling positions, which have distinct CFA locations.
    result: dict[str, np.ndarray] = {}
    for channel, samples in planes.items():
        if len(samples) == 1:
            result[channel] = samples[0].copy()
        elif samples:
            result["G1"] = samples[0].copy()
            result["G2"] = samples[1].copy()
    return result
