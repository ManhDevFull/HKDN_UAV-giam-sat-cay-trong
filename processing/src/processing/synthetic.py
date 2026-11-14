"""Create deterministic Bayer mosaic fixtures; no camera data required."""

import argparse
import json
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
    parser.add_argument("--week2", action="store_true", help="Create a three-session calibration demo with measured ground truth")
    args = parser.parse_args()
    if args.week2:
        make_calibration_demo(args.output)
        print(f"Wrote synthetic calibration demo to {args.output}")
        return
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / '.gitignore').write_text('*\n', encoding='utf-8')
    mosaic, flat = make_synthetic_mosaic(args.size)
    np.save(args.output / "mosaic.npy", mosaic)
    np.save(args.output / "flat.npy", flat)
    print(f"Wrote synthetic 12-bit Bayer mosaic to {args.output}")


def make_calibration_demo(output: Path) -> None:
    """Small reproducible fixture; these reflectances are NOT real MAPIR values."""
    output.mkdir(parents=True, exist_ok=False)
    (output / '.gitignore').write_text('*\n', encoding='utf-8')
    rng = np.random.default_rng(42)
    shade = radial_flat((96, 96), strength=0.3)
    black = 64.0
    np.save(output / "flat.npy", 1000 * shade + black)
    sessions = []
    for name, scale in (("morning", 1800), ("noon", 3200), ("afternoon", 2400)):
        folder = output / name
        folder.mkdir()
        target = np.full((96, 96), 0.1)
        target[:, 48:] = 0.7
        scene = np.empty((96, 96))
        for (row, col), value in zip(((0, 0), (0, 1), (1, 0), (1, 1)), (0.35, 0.4, 0.4, 0.55)):
            scene[row::2, col::2] = value
        for filename, reflectance in (("target", target), ("scene", scene)):
            mosaic = reflectance * scale * shade + black + rng.normal(0, 0.2, shade.shape)
            np.save(folder / f"{filename}.npy", mosaic.astype(np.float32))
        sessions.append({"id": name, "images": [f"{name}/scene.npy"],
                         "target": f"{name}/target.npy", "exposure_confirmed": True,
                         "panels": [
                             {"roi": [8, 8, 32, 32], "reflectance": {"R": 0.1, "G": 0.1, "NIR": 0.1}},
                             {"roi": [56, 8, 32, 32], "reflectance": {"R": 0.7, "G": 0.7, "NIR": 0.7}}],
                         "checks": [{"image": f"{name}/scene.npy", "object_id": "demo-object",
                                     "roi": [24, 24, 48, 48]}]})
    config = {"schema_version": 1, "filter": "RGN", "pattern": "RGGB", "black_level": black,
              "flat": "flat.npy", "sessions": sessions}
    (output / "calibration.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
