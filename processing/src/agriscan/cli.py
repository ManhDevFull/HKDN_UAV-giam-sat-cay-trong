"""Command-line interface for AgriScan (Items 1, 2, 3)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agriscan.io.image_validator import validate_survey_folder
from agriscan.io.metadata_reader import read_metadata
from agriscan.io.raw_reader import read_raw
from agriscan.pipeline.runner import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="AgriScan Group B CLI")
    subparsers = parser.add_subparsers(dest="command")

    # 1. check-config / process
    p_run = subparsers.add_parser("run", help="Load config, validate survey, and test RAW decoding")
    p_run.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    p_run.add_argument("--input", type=Path, default=None, help="Override survey input directory")

    # 2. validate survey folder
    p_val = subparsers.add_parser("validate", help="Validate a Group A survey folder and metadata.json")
    p_val.add_argument("survey_dir", type=Path, help="Path to survey directory (e.g. ../assets)")

    # 3. inspect / decode a single RAW file
    p_raw = subparsers.add_parser("read-raw", help="Decode and inspect a MAPIR .RAW file")
    p_raw.add_argument("raw_path", type=Path, help="Path to .RAW file")
    p_raw.add_argument("--metadata", type=Path, default=None, help="Optional path to metadata.json")

    args = parser.parse_args()

    if args.command == "validate":
        report = validate_survey_folder(args.survey_dir)
        print(json.dumps(report, indent=2, ensure_ascii=False))
    elif args.command == "read-raw":
        survey_meta = read_metadata(args.metadata, strict=False) if args.metadata else None
        _, raw_info = read_raw(args.raw_path, survey_metadata=survey_meta)
        print(json.dumps(raw_info, indent=2, ensure_ascii=False))
    else:
        config_path = getattr(args, "config", Path("configs/default.yaml"))
        input_dir = getattr(args, "input", None)
        run_pipeline(config_path=config_path, survey_dir=input_dir)


if __name__ == "__main__":
    main()
