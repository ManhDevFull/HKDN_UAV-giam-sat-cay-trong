"""Pipeline runner connecting configuration, validation, RAW reading, and band extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agriscan.calibration.band_extractor import extract_rgn_bands, save_extracted_bands
from agriscan.io.image_validator import validate_survey_folder
from agriscan.io.metadata_reader import read_metadata
from agriscan.io.raw_reader import read_raw
from agriscan.pipeline.steps import load_config


def run_pipeline(
    config_path: str | Path = "configs/default.yaml",
    survey_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load configuration, validate input survey folder, decode sample RAW, and extract RGN bands."""
    config = load_config(config_path)

    camera_cfg_path = Path(config_path).parent / "camera.yaml"
    camera_config = load_config(camera_cfg_path) if camera_cfg_path.exists() else None

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

            extraction = extract_rgn_bands(
                mosaic,
                camera_config=camera_config,
                survey_metadata=meta,
            )
            extraction["metadata"]["source_file"] = raw_meta.get("source")
            extraction["metadata"]["decoder"] = raw_meta.get("decoder")

            if config.get("processing", {}).get("save_intermediate", True):
                inter_dir = Path(config["paths"]["intermediate"]) / raw_files[0].stem
                band_meta = save_extracted_bands(extraction, inter_dir)
                result["sample_bands"] = band_meta
                band_names = ", ".join(
                    f"{k}({v['wavelength_nm']}nm)" for k, v in band_meta["bands"].items()
                )
                print(f"Extracted bands saved to {inter_dir}: {band_names}")

    return result
