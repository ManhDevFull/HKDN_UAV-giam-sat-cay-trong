"""Read and validate survey metadata.json files from Group A."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

VALID_ACQUISITION_METHODS = {"handheld", "pole", "fixed"}
UNVERIFIED_FILTER_PLACEHOLDERS = {"", "VERIFY_ACTUAL_FILTER", "UNKNOWN", "TBD"}


class MetadataValidationError(ValueError):
    """Raised when survey metadata fails schema or domain validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_metadata(data: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    """Validate survey metadata dictionary against Group A/B contract.

    Returns:
        (is_valid, errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return False, ["Metadata root must be a JSON object"], warnings

    # 1. survey_id and plot_id
    for field in ("survey_id", "plot_id"):
        val = data.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"Missing or empty required string field: '{field}'")

    # 2. ISO 8601 timestamps
    dt_start_raw = data.get("datetime_start")
    dt_end_raw = data.get("datetime_end")
    dt_start = None
    dt_end = None

    if not isinstance(dt_start_raw, str) or not dt_start_raw.strip():
        errors.append("Missing or empty 'datetime_start'")
    else:
        try:
            dt_start = datetime.fromisoformat(dt_start_raw)
        except ValueError:
            errors.append(f"Invalid ISO 8601 format for 'datetime_start': {dt_start_raw}")

    if not isinstance(dt_end_raw, str) or not dt_end_raw.strip():
        errors.append("Missing or empty 'datetime_end'")
    else:
        try:
            dt_end = datetime.fromisoformat(dt_end_raw)
        except ValueError:
            errors.append(f"Invalid ISO 8601 format for 'datetime_end': {dt_end_raw}")

    if dt_start is not None and dt_end is not None and dt_start > dt_end:
        errors.append("'datetime_start' must not be after 'datetime_end'")

    # 3. acquisition_method
    method = data.get("acquisition_method")
    if method not in VALID_ACQUISITION_METHODS:
        errors.append(
            f"Invalid 'acquisition_method': {method!r} (expected one of {sorted(VALID_ACQUISITION_METHODS)})"
        )

    # 4. camera model, filter, and bands
    camera = data.get("camera")
    if not isinstance(camera, dict):
        errors.append("Missing or invalid 'camera' object")
    else:
        model = camera.get("model")
        if not isinstance(model, str) or not model.strip():
            errors.append("Missing or empty 'camera.model'")

        cam_filter = camera.get("filter")
        if (
            not isinstance(cam_filter, str)
            or cam_filter.strip().upper() in UNVERIFIED_FILTER_PLACEHOLDERS
        ):
            errors.append(f"Camera filter is not verified: {cam_filter!r}")

        bands = camera.get("bands")
        if not isinstance(bands, dict) or not bands:
            errors.append("Missing or invalid 'camera.bands' mapping")
        else:
            verified_bands = {
                k: v for k, v in bands.items() if isinstance(v, (int, float)) and v > 0
            }
            if not verified_bands:
                warnings.append("No numeric wavelengths confirmed in 'camera.bands'")

        serial = camera.get("serial")
        if serial in (None, "", "..."):
            warnings.append("Camera serial number is not specified or placeholder ('...')")

    # 5. height_m and gsd_cm
    height_m = data.get("height_m")
    if height_m is not None and (not isinstance(height_m, (int, float)) or height_m <= 0):
        errors.append(f"'height_m' must be a positive number or null, got {height_m!r}")

    gsd_cm = data.get("gsd_cm")
    if gsd_cm is not None and (not isinstance(gsd_cm, (int, float)) or gsd_cm <= 0):
        errors.append(f"'gsd_cm' must be a positive number or null, got {gsd_cm!r}")

    # 6. image_count
    image_count = data.get("image_count")
    if not isinstance(image_count, int) or isinstance(image_count, bool) or image_count < 0:
        errors.append(f"'image_count' must be a non-negative integer, got {image_count!r}")

    # 7. calibration_target
    cal_target = data.get("calibration_target")
    if not isinstance(cal_target, dict):
        warnings.append("Missing 'calibration_target' section in metadata")
    else:
        for key in ("before", "after"):
            if not cal_target.get(key):
                warnings.append(f"Missing 'calibration_target.{key}' path in metadata")

    return len(errors) == 0, errors, warnings


def read_metadata(metadata_path: str | Path, *, strict: bool = True) -> dict[str, Any]:
    """Read and validate a survey metadata.json file.

    Args:
        metadata_path: Path to metadata.json (or survey directory containing metadata.json).
        strict: If True, raise MetadataValidationError when validation fails.

    Returns:
        Parsed metadata dictionary with an '_validation' summary key when strict=False.
    """
    path = Path(metadata_path)
    if path.is_dir():
        path = path / "metadata.json"

    if not path.exists():
        raise FileNotFoundError(f"Metadata file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in metadata file {path}: {exc}") from exc

    is_valid, errors, warnings = validate_metadata(data)
    if strict and not is_valid:
        raise MetadataValidationError(errors)

    data["_validation"] = {
        "is_valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "source_path": str(path.resolve()),
    }
    return data
