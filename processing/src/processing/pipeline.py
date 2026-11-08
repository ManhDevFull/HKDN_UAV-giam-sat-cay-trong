"""Small week-one RAW-to-corrected-channel pipeline."""

import json
from pathlib import Path

import numpy as np
from PIL import Image

from .raw import decode_raw, split_bayer_channels
from .vignetting import correct_vignetting


def _save_plane(path: Path, plane: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # PNG is for inspection only; retain numeric planes as .npy for analysis.
    np.save(path.with_suffix(".npy"), plane)
    high = np.iinfo(np.uint16).max
    scaled = np.clip(plane / max(float(plane.max()), 1.0) * high, 0, high).astype(np.uint16)
    Image.fromarray(scaled).save(path)


def process_mosaic(mosaic: np.ndarray, output_dir: Path, pattern: str = "RGGB") -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    channels = split_bayer_channels(mosaic, pattern)
    stats: dict[str, object] = {"pattern": pattern, "channels": {}}
    for name, channel in channels.items():
        flat = np.ones(channel.shape, dtype=np.float32)
        corrected = correct_vignetting(channel, flat)
        _save_plane(output_dir / f"{name}.png", corrected)
        stats["channels"][name] = {
            "shape": list(channel.shape),
            "min": float(channel.min()),
            "max": float(channel.max()),
        }
    (output_dir / "metadata.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def process_raw(input_path: Path, output_dir: Path, pattern: str = "RGGB") -> dict[str, object]:
    mosaic, metadata = decode_raw(input_path)
    result = process_mosaic(mosaic, output_dir, pattern)
    result["source_metadata"] = metadata
    (output_dir / "metadata.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
