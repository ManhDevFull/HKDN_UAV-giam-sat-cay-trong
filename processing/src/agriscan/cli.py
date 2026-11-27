"""Command-line interface for AgriScan (Items 1, 2, 3, 4)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agriscan.calibration.band_extractor import extract_bands_from_raw
from agriscan.io.image_validator import validate_survey_folder
from agriscan.io.metadata_reader import read_metadata
from agriscan.io.raw_reader import read_raw
from agriscan.pipeline.runner import run_pipeline
from agriscan.pipeline.steps import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="AgriScan Group B CLI")
    subparsers = parser.add_subparsers(dest="command")

    # 1. check-config / process
    p_run = subparsers.add_parser("run", help="Load config, validate survey, decode RAW, and extract bands")
    p_run.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    p_run.add_argument("--input", type=Path, default=None, help="Override survey input directory")

    # 2. validate survey folder
    p_val = subparsers.add_parser("validate", help="Validate a Group A survey folder and metadata.json")
    p_val.add_argument("survey_dir", type=Path, help="Path to survey directory (e.g. ../assets)")

    # 3. inspect / decode a single RAW file
    p_raw = subparsers.add_parser("read-raw", help="Decode and inspect a MAPIR .RAW file")
    p_raw.add_argument("raw_path", type=Path, help="Path to .RAW file")
    p_raw.add_argument("--metadata", type=Path, default=None, help="Optional path to metadata.json")

    # 4. extract spectral bands (Red 660nm, Green 550nm, NIR 850nm) to .tif
    p_bands = subparsers.add_parser(
        "extract-bands",
        help="Extract confirmed RGN spectral bands (red.tif, green.tif, nir.tif) from a RAW file",
    )
    p_bands.add_argument("raw_path", type=Path, help="Path to .RAW file")
    p_bands.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for red.tif, green.tif, nir.tif (default: data/intermediate/<image_stem>)",
    )
    p_bands.add_argument("--metadata", type=Path, default=None, help="Optional path to metadata.json")
    p_bands.add_argument(
        "--camera-config",
        type=Path,
        default=Path("configs/camera.yaml"),
        help="Path to camera.yaml configuration",
    )
    p_bands.add_argument(
        "--full-res",
        action="store_true",
        help="Interpolate extracted bands to full sensor resolution (3000x4000) instead of native 2x2 plane (1500x2000)",
    )

    args = parser.parse_args()

    if args.command == "validate":
        report = validate_survey_folder(args.survey_dir)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.command == "read-raw":
        survey_meta = read_metadata(args.metadata, strict=False) if args.metadata else None
        _, raw_info = read_raw(args.raw_path, survey_metadata=survey_meta)
        print(json.dumps(raw_info, indent=2, ensure_ascii=False))
    elif args.command == "extract-bands":
        survey_meta = read_metadata(args.metadata, strict=False) if args.metadata else None
        cam_cfg = load_config(args.camera_config) if args.camera_config and args.camera_config.exists() else None
        out_dir = args.output or (Path("data/intermediate") / args.raw_path.stem)
        keep_half = False if args.full_res else None
        band_report = extract_bands_from_raw(
            args.raw_path,
            out_dir,
            camera_config=cam_cfg,
            survey_metadata=survey_meta,
            keep_half_resolution=keep_half,
        )
        print(json.dumps(band_report, indent=2, ensure_ascii=False))
    else:
        config_path = getattr(args, "config", Path("configs/default.yaml"))
        input_dir = getattr(args, "input", None)
        run_pipeline(config_path=config_path, survey_dir=input_dir)


if __name__ == "__main__":
    main()
