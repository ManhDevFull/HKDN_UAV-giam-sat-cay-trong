"""RAW decoding adapters. RAW mosaics are kept separate from rendered RGB."""

from pathlib import Path

import numpy as np


def decode_raw(path: Path) -> tuple[np.ndarray, dict[str, object]]:
    """Return the sensor mosaic and basic metadata from a camera RAW file."""
    try:
        import rawpy
    except ImportError as exc:
        raise RuntimeError("RAW decoding requires the optional dependency: pip install -e '.[raw]'") from exc

    with rawpy.imread(str(path)) as raw:
        mosaic = raw.raw_image_visible.copy()
        metadata: dict[str, object] = {
            "source": path.name,
            "width": int(mosaic.shape[1]),
            "height": int(mosaic.shape[0]),
            "cfa_pattern": raw.raw_pattern.tolist(),
            "color_desc": raw.color_desc.decode("ascii", errors="replace"),
            "black_level_per_channel": list(raw.black_level_per_channel),
            "white_level": int(raw.white_level),
        }
    return mosaic, metadata


def split_bayer_channels(mosaic: np.ndarray, pattern: str = "RGGB") -> dict[str, np.ndarray]:
    """Split a 2x2 Bayer mosaic into named planes without demosaicing."""
    if mosaic.ndim != 2 or mosaic.shape[0] % 2 or mosaic.shape[1] % 2:
        raise ValueError("Expected a 2D mosaic with even width and height")
    pattern = pattern.upper()
    if len(pattern) != 4 or set(pattern) - set("RGB"):
        raise ValueError("pattern must contain four Bayer positions, e.g. RGGB")
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
