"""Command-line entry point."""

import argparse
from pathlib import Path
import sys

from .pipeline import run_batch


def default_output(input_path: Path) -> Path:
    base = Path('processing/output') if Path('processing/pyproject.toml').is_file() else Path('output')
    source = input_path.resolve()
    return base / (source.name if source.is_dir() else source.stem)


def main() -> None:
    parser = argparse.ArgumentParser(description="Correct Survey3 RAW, use JPEG previews/EXIF, export a raster manifest")
    parser.add_argument("input", type=Path, help="Group A input directory, RAW, JPEG preview, or NPY mosaic")
    parser.add_argument("--output", type=Path, help="Stable output folder, replaced on success (default: processing/output/INPUT_NAME)")
    parser.add_argument("--calibration", type=Path, help="JSON config (default: INPUT/calibration.json if present)")
    parser.add_argument("--settings", type=Path, help="Software parameters; defaults are bundled with the package")
    parser.add_argument("--mode", choices=["auto", "relative", "panel"], default="auto",
                        help="auto: factory relative correction unless a panel config exists")
    parser.add_argument("--pattern", choices=["RGGB", "BGGR", "GRBG", "GBRG"], help="NPY Bayer pattern; camera RAW uses decoder metadata")
    parser.add_argument("--require-validation", action="store_true", help="Exit 2 unless independent 3-session repeatability is <5%%")
    args = parser.parse_args()
    output = args.output or default_output(args.input)
    try:
        result = run_batch(args.input, output, config_path=args.calibration, pattern=args.pattern,
                           settings_path=args.settings, mode=args.mode, require_validation=args.require_validation)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    print(f"Processed {result['processed_count']}/{result['input_count']}; "
          f"RAW corrected: {result['relative_corrected_count']}; JPEG preview-only: {result['preview_only_count']}")
    print(f"Factory lens correction: {result['factory_flat_corrected_count']}; "
          f"paired exposure normalization: {result['exposure_normalized_count']}; low signal: {result['low_signal_count']}")
    if result['mode'] == 'panel':
        print(f"Panel calibrated: {result['calibrated_count']}; three-session check: {result['validation']['status']}")
    print("Absolute reflectance accuracy <5%: not verified; cross-survey comparison is disabled")
    if result['previous_output_retained']:
        print(f"New run did not pass; previous output kept unchanged: {output}")
    else:
        print(f"Group C manifest: {output / 'manifest.json'}")
        print(f"Report: {output / 'summary.json'}")
    if result["failed_count"]:
        sys.exit(1)
    if args.require_validation and result["validation"]["status"] != "passed":
        sys.exit(2)


if __name__ == "__main__":
    main()
