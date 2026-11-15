"""Pipeline runner connecting configuration, validation, and RAW reading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agriscan.io.image_validator import validate_survey_folder
from agriscan.io.metadata_reader import read_metadata
from agriscan.io.raw_reader import read_raw
from agriscan.pipeline.steps import load_config


def run_pipeline(
    config_path: str | Path = "configs/default.yaml",
    survey_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load configuration, validate input survey folder, and decode the first RAW sample."""
    config = load_config(config_path)

    print("=" * 45)
    print("AGRISCAN PROCESSING")
    print("=" * 45)
    print("Project:", config["project"]["name"])
    print("Version:", config["project"]["version"])

    target_input = Path(survey_dir) if survey_dir is not None else Path(config["paths"]["input"])
    print("Input:", target_input)
    print("Output:", config["paths"]["output"])
    print("Configuration loaded successfully!")

    result: dict[str, Any] = {"config": config}

    if target_input.exists() and (target_input / "metadata.json").exists():
        validation = validate_survey_folder(target_input)
        result["validation"] = validation
        print(
            f"Validation status: {validation['status']} "
            f"(RAW={validation['counts']['raw_count']}, JPG={validation['counts']['jpg_count']})"
        )

        raw_dir = target_input / "raw"
        raw_files = sorted(raw_dir.glob("*.RAW")) if raw_dir.exists() else []
        if raw_files:
            meta = read_metadata(target_input / "metadata.json", strict=False)
            mosaic, raw_meta = read_raw(raw_files[0], survey_metadata=meta)
            result["sample_raw"] = raw_meta
            print(
                f"Sample RAW decoded: {raw_files[0].name} -> "
                f"shape={mosaic.shape}, dtype={mosaic.dtype}, "
                f"min={raw_meta['pixel_stats']['min']}, max={raw_meta['pixel_stats']['max']}"
            )

    return result
