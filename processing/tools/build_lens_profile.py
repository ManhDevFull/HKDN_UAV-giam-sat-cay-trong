"""Rebuild the compact Survey3W lens profile from pinned MAPIR measurements.

Run with the processing virtualenv. Downloaded TIFFs stay in ignored data/;
only the generated coefficients and the upstream data license are distributed.
The reported errors measure numerical fit error against the factory flat field,
not reflectance accuracy or accuracy on an individual physical camera.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f127afad0e31370cbb28d1783435cedafd2fd915"
REPOSITORY = "https://github.com/mapircamera/camera-scripts"
RAW_BASE = f"https://raw.githubusercontent.com/mapircamera/camera-scripts/{COMMIT}/"
SOURCE_DIRECTORY = "Vignette_Correction_Survey3/flatFields/S3W/"
SHA256 = {
    "R": "34f2f5e9514e998a7718434d6e2a67f43da8c452ed3645adfa44584dfd3b0d84",
    "G": "587fc929640617c0739de3167fec504e1ed8c85c7e2323eda096d631efb25fd7",
    "B": "587fc929640617c0739de3167fec504e1ed8c85c7e2323eda096d631efb25fd7",
}
SENSOR_SHAPE = (3000, 4000)
LICENSE_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def download(url: str, path: Path, expected_sha256: str | None = None) -> str:
    """Download a pinned measurement, keeping incomplete transfers separate."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        partial = path.with_suffix(path.suffix + ".part")
        try:
            with urlopen(url, timeout=60) as response, partial.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"SHA-256 mismatch for {path.name}; remove it and retry")
    return digest


def normalize(indices: np.ndarray, length: int) -> np.ndarray:
    return 2.0 * indices.astype(np.float64) / (length - 1) - 1.0


def fit_field(field: np.ndarray, degree: int) -> tuple[np.ndarray, dict]:
    """Fit a smooth separable Chebyshev surface; check a disjoint pixel grid."""
    height, width = field.shape
    # Native positions including the last row/column, rather than rescaling a
    # thumbnail; this keeps the model in the full sensor coordinate system.
    # An odd stride samples both Bayer parities. An even stride would sample
    # almost exclusively one parity and bias this smooth full-sensor model.
    rows = np.unique(np.append(np.arange(0, height, 19), height - 1))
    cols = np.unique(np.append(np.arange(0, width, 19), width - 1))
    x_basis = np.polynomial.chebyshev.chebvander(normalize(cols, width), degree)
    y_basis = np.polynomial.chebyshev.chebvander(normalize(rows, height), degree)
    samples = field[np.ix_(rows, cols)].astype(np.float64)
    # samples = Y @ C.T @ X.T; fit along each axis without a very large 2D
    # design matrix. C[i,j] multiplies T_i(x)*T_j(y).
    along_y = np.linalg.lstsq(y_basis, samples, rcond=None)[0]
    coefficients = np.linalg.lstsq(x_basis, along_y.T, rcond=None)[0]

    # Every validation position differs from the training grid. Include all
    # edge positions on this grid so the model is checked at its boundaries.
    check_rows = np.setdiff1d(np.arange(0, height, 7), rows)
    check_cols = np.setdiff1d(np.arange(0, width, 7), cols)
    x_check = np.polynomial.chebyshev.chebvander(normalize(check_cols, width), degree)
    y_check = np.polynomial.chebyshev.chebvander(normalize(check_rows, height), degree)
    prediction = y_check @ coefficients.T @ x_check.T
    observed = field[np.ix_(check_rows, check_cols)]
    if np.any(prediction <= 0) or not np.all(np.isfinite(prediction)):
        raise ValueError("Fitted attenuation must be finite and positive")
    # Applying /prediction instead of /observed changes a corrected pixel by
    # observed/prediction - 1. Report this correction error, rather than the
    # numerically slightly different error in fitted attenuation itself.
    relative_error = np.abs(observed / prediction - 1.0)

    # Also evaluate every native pixel to detect boundary oscillation or a
    # negative model that a held-out sample could miss. Keep memory bounded.
    all_x = np.polynomial.chebyshev.chebvander(
        normalize(np.arange(width), width), degree
    )
    model_min, model_max = float("inf"), float("-inf")
    native_max_error = 0.0
    for start in range(0, height, 100):
        stop = min(start + 100, height)
        block_y = np.polynomial.chebyshev.chebvander(
            normalize(np.arange(start, stop), height), degree
        )
        block = block_y @ coefficients.T @ all_x.T
        model_min = min(model_min, float(block.min()))
        model_max = max(model_max, float(block.max()))
        native_max_error = max(
            native_max_error, float(np.max(np.abs(field[start:stop] / block - 1.0)))
        )
    if model_min <= 0:
        raise ValueError("Fitted attenuation is nonpositive at native geometry")

    parity_checks = {}
    for row_parity in (0, 1):
        for col_parity in (0, 1):
            errors = relative_error[np.ix_(
                check_rows % 2 == row_parity, check_cols % 2 == col_parity
            )]
            parity_checks[f"row{row_parity}_col{col_parity}"] = {
                "pixel_count": int(errors.size),
                "relative_error_p95": float(np.quantile(errors, 0.95)),
                "relative_error_p99": float(np.quantile(errors, 0.99)),
                "relative_error_max": float(errors.max()),
            }

    return coefficients, {
        "metric": "abs(measured_attenuation / fitted_attenuation - 1)",
        "scope": "numerical approximation of manufacturer flat field only",
        "training_pixel_count": int(samples.size),
        "held_out_pixel_count": int(relative_error.size),
        "held_out_relative_rmse": float(np.sqrt(np.mean(relative_error**2))),
        "held_out_relative_error_p95": float(np.quantile(relative_error, 0.95)),
        "held_out_relative_error_p99": float(np.quantile(relative_error, 0.99)),
        "held_out_relative_error_max": float(relative_error.max()),
        "held_out_by_pixel_parity": parity_checks,
        "all_native_pixels_relative_error_max": native_max_error,
        "measured_attenuation_min": float(field.min()),
        "measured_attenuation_max": float(field.max()),
        "fitted_attenuation_min": model_min,
        "fitted_attenuation_max": model_max,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--degree", type=int, default=12)
    parser.add_argument("--cache", type=Path, default=ROOT / "data/reference/mapir")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "src/processing/profiles/survey3w.json",
    )
    args = parser.parse_args()
    if not 2 <= args.degree <= 16:
        parser.error("degree must be between 2 and 16")
    profile = {
        "schema_version": 1,
        "profile_id": "mapir-survey3w-factory-flat-chebyshev-v1",
        "camera_model": "Survey3W",
        "sensor_shape": list(SENSOR_SHAPE),
        "basis": "chebyshev2d",
        "degree": args.degree,
        "coordinate_normalization": {"x": [0, 3999], "y": [0, 2999]},
        "coefficient_convention": "coefficients[i][j] * T_i(x) * T_j(y)",
        "operation": "divide_by_attenuation",
        "channels": {},
        "provenance": {
            "author": "MAPIR Camera",
            "repository": REPOSITORY,
            "commit": COMMIT,
            "flat_field_directory": f"{REPOSITORY}/tree/{COMMIT}/{SOURCE_DIRECTORY}",
            "reference_implementation": (
                f"{REPOSITORY}/blob/{COMMIT}/"
                "Vignette_Correction_Survey3/Vignette_Correction.py"
            ),
            "builder": "processing/tools/build_lens_profile.py",
            "source_license": "GPL-3.0-only",
            "license_file": "MAPIR-LICENSE.txt",
            "license_url": f"{REPOSITORY}/blob/{COMMIT}/LICENSE",
            "license_sha256": LICENSE_SHA256,
            "note": (
                "Upstream README says MIT, but the pinned LICENSE is GPL-3.0; "
                "this derived measurement profile retains that license. "
                "No upstream executable code is copied."
            ),
        },
        "limitations": [
            "Factory lens flat fields are generic S3W measurements, not a "
            "measurement of this individual camera or a scene reflectance standard.",
            "The fit is smooth; per-pixel defects and flat-field measurement "
            "noise are intentionally not reproduced.",
            "Use only at native Survey3W 4000x3000 sensor geometry, with the "
            "original orientation and no crop or lens correction applied.",
            "Apply to linear RAW signal after its separately determined black "
            "level. TIFF-domain dark constants from the upstream script are "
            "not RAW black-level estimates.",
            "Do not automatically apply this RAW lens profile to JPEG: its "
            "in-camera nonlinear processing and existing lens correction are unknown.",
            "No RGN spectral unmixing or NIR cross-talk correction is encoded.",
            "Numerical fit errors are not an estimate of reflectance accuracy "
            "and do not establish a below-5-percent scene error.",
        ],
    }
    for channel in ("R", "G", "B"):
        name = f"Average Flat Field Correction Image{channel}.tif"
        source_url = RAW_BASE + quote(SOURCE_DIRECTORY + name)
        cache_path = args.cache / name
        digest = download(source_url, cache_path, SHA256[channel])
        with Image.open(cache_path) as image:
            field = np.asarray(image, dtype=np.float32)
        if field.shape != SENSOR_SHAPE or not np.all(np.isfinite(field)) or np.any(field <= 0):
            raise ValueError(f"Invalid measured flat field: {cache_path}")
        coefficients, validation = fit_field(field, args.degree)
        profile["channels"][channel] = {
            "source_url": source_url,
            "source_sha256": digest,
            "source_size_bytes": cache_path.stat().st_size,
            "source_dtype": str(field.dtype),
            "coefficients": coefficients.tolist(),
            "validation": validation,
        }
        print(
            f"{channel}: p95={validation['held_out_relative_error_p95']:.3%}, "
            f"p99={validation['held_out_relative_error_p99']:.3%}, "
            f"native max={validation['all_native_pixels_relative_error_max']:.3%}",
            flush=True,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    download(RAW_BASE + "LICENSE", args.output.parent / "MAPIR-LICENSE.txt", LICENSE_SHA256)
    args.output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"Profile: {args.output}")


if __name__ == "__main__":
    main()
