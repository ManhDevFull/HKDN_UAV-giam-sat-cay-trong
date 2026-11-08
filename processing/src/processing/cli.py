"""Command-line entry point."""

import argparse
from pathlib import Path

import numpy as np

from .pipeline import process_mosaic, process_raw


def main() -> None:
    parser = argparse.ArgumentParser(description="Decode RAW, split Bayer channels, and correct vignetting")
    parser.add_argument("input", type=Path, help="Camera RAW file or synthetic .npy mosaic")
    parser.add_argument("--output", type=Path, default=Path("output/run-001"))
    parser.add_argument("--pattern", default="RGGB", help="Bayer pattern (default: RGGB)")
    args = parser.parse_args()
    if args.input.suffix.lower() == ".npy":
        process_mosaic(np.load(args.input), args.output, args.pattern)
    else:
        process_raw(args.input, args.output, args.pattern)
    print(f"Processing complete: {args.output}")
