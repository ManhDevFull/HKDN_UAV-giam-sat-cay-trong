"""Command-line entry point."""

import argparse
from pathlib import Path
import sys

from .pipeline import run_batch


def main() -> None:
    parser = argparse.ArgumentParser(description="Process RAW images and calibrate reflectance per capture session")
    parser.add_argument("input", type=Path, help="Input directory (e.g. ../assets), one RAW, or one NPY mosaic")
    parser.add_argument("--output", type=Path, required=True, help="New output directory outside the input directory")
    parser.add_argument("--calibration", type=Path, help="JSON config (default: INPUT/calibration.json if present)")
    parser.add_argument("--pattern", choices=["RGGB", "BGGR", "GRBG", "GBRG"], help="NPY Bayer pattern; camera RAW uses decoder metadata")
    parser.add_argument("--require-validation", action="store_true", help="Exit 2 unless independent 3-session repeatability is <5%%")
    args = parser.parse_args()
    try:
        result = run_batch(args.input, args.output, config_path=args.calibration, pattern=args.pattern)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Processed {result['processed_count']}/{result['input_count']}; "
          f"reflectance calibrated: {result['calibrated_count']}; "
          f"three-session check: {result['validation']['status']}")
    print(f"Report: {args.output / 'summary.json'}")
    if result["failed_count"]:
        sys.exit(1)
    if args.require_validation and result["validation"]["status"] != "passed":
        sys.exit(2)


if __name__ == "__main__":
    main()
