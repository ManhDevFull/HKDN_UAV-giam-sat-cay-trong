"""Create deterministic Bayer mosaic fixtures; no camera data required."""

import argparse
from pathlib import Path

import numpy as np

from .vignetting import radial_flat


def make_synthetic_mosaic(size: int = 512, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    if size < 8 or size % 2:
        raise ValueError("size must be an even number >= 8")
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:size, 0:size]
    scene = np.clip(0.35 + 0.2 * np.sin(x / 35) + 0.15 * np.cos(y / 41), 0.05, 0.9)
    mosaic = (scene * radial_flat((size, size)) * 4095 + rng.normal(0, 5, (size, size)))
    return np.clip(mosaic, 0, 4095).astype(np.uint16), radial_flat((size, size))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/synthetic"))
    parser.add_argument("--size", type=int, default=512)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    mosaic, flat = make_synthetic_mosaic(args.size)
    np.save(args.output / "mosaic.npy", mosaic)
    np.save(args.output / "flat.npy", flat)
    print(f"Wrote synthetic 12-bit Bayer mosaic to {args.output}")


if __name__ == "__main__":
    main()
