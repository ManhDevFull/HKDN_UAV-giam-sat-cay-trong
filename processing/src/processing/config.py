"""Local calibration configuration; paths are relative to the input directory."""

import json
from pathlib import Path

import numpy as np


def asset_path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("Expected a nonempty path relative to the input directory")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f"Calibration path must stay inside the input directory: {value}")
    if not path.is_file():
        raise ValueError(f"Missing calibration input: {value}")
    return path


def load_config(path: Path | None) -> dict:
    if path is None:
        return {"filter": "RGN", "sessions": []}
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] != 1:
        raise ValueError("Calibration config must be an object with schema_version: 1")
    allowed = {"schema_version", "filter", "pattern", "black_level", "flat", "sessions"}
    if set(config) - allowed:
        raise ValueError(f"Unknown calibration settings: {sorted(set(config) - allowed)}")
    if config.get("filter", "RGN") not in ("RGN", "RGB"):
        raise ValueError("filter must be RGN or RGB")
    pattern = config.get("pattern")
    if pattern is not None and pattern not in ("RGGB", "BGGR", "GRBG", "GBRG"):
        raise ValueError("pattern must be RGGB, BGGR, GRBG, GBRG or null")
    flat = config.get("flat")
    if flat is not None and (not isinstance(flat, str) or not flat):
        raise ValueError("flat must be a nonempty input-relative path or null")
    black = config.get("black_level")
    if black is not None and (isinstance(black, bool) or not isinstance(black, (int, float))
                              or not np.isfinite(black) or black < 0):
        raise ValueError("black_level must be a finite, nonnegative number or null")
    sessions = config.get("sessions", [])
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list")
    ids = set()
    for session in sessions:
        if not isinstance(session, dict):
            raise ValueError("Each session must be an object")
        extra = set(session) - {"id", "images", "target", "panels", "checks", "exposure_confirmed"}
        if extra:
            raise ValueError(f"Unknown session settings: {sorted(extra)}")
        name = session.get("id")
        if not isinstance(name, str) or not name or name in ids:
            raise ValueError("Session ids must be unique, nonempty strings")
        ids.add(name)
        if session.get("exposure_confirmed") is not True:
            raise ValueError(f"{name}: confirm the SAME exposure/ISO and lighting for target and scene images")
        if not isinstance(session.get("images"), list) or not session["images"]:
            raise ValueError(f"{name}: images must contain relative file paths or glob patterns")
        for pattern in session["images"]:
            if not isinstance(pattern, str) or not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
                raise ValueError(f"{name}: image patterns must stay inside the input directory")
        if not isinstance(session.get("panels"), list) or len(session["panels"]) < 2:
            raise ValueError(f"{name}: at least two panels with distinct measured reflectances are required")
        if not isinstance(session.get("checks", []), list):
            raise ValueError(f"{name}: checks must be a list")
    return config


def plane_roi(roi: list[int], shape: tuple[int, int]) -> tuple[slice, slice]:
    """Map an even [x,y,width,height] RAW ROI onto each half-resolution plane."""
    if (not isinstance(roi, list) or len(roi) != 4
            or any(type(v) is not int or v < 0 or v % 2 for v in roi)):
        raise ValueError("ROI must be [x,y,width,height] in full RAW pixels, all even integers")
    x, y, width, height = roi
    if width < 8 or height < 8 or x + width > shape[1] * 2 or y + height > shape[0] * 2:
        raise ValueError("ROI must fit the RAW image and cover at least 8x8 RAW pixels")
    return slice(y // 2, (y + height) // 2), slice(x // 2, (x + width) // 2)


def sample_roi(plane: np.ndarray, roi: list[int]) -> float:
    sample = plane[plane_roi(roi, plane.shape)]
    if not np.all(np.isfinite(sample)):
        raise ValueError("ROI includes saturated or invalid pixels; choose an unsaturated region")
    return float(np.mean(sample, dtype=np.float64))
