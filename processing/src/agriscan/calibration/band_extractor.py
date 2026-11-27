"""Step 2 (M2.1 Part 2) — Extract spectral bands from decoded Bayer mosaic according to confirmed filter."""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import rasterio
from rasterio.errors import NotGeoreferencedWarning
from rasterio.transform import Affine

from agriscan.io.raw_reader import read_raw

SUPPORTED_FILTERS: dict[str, dict[str, dict[str, Any]]] = {
    "RGN": {
        "red": {"wavelength_nm": 660, "bayer_position": "R"},
        "green": {"wavelength_nm": 550, "bayer_position": "G"},
        "nir": {"wavelength_nm": 850, "bayer_position": "B"},
    }
}


def _split_cfa_positions(mosaic: np.ndarray, cfa_pattern: str = "RGGB") -> dict[str, list[np.ndarray]]:
    """Split a 2D Bayer mosaic into its 2x2 sub-planes keyed by CFA letter (R, G, B)."""
    if mosaic.ndim != 2 or mosaic.shape[0] % 2 != 0 or mosaic.shape[1] % 2 != 0:
        raise ValueError(f"Expected 2D mosaic with even height and width, got shape {mosaic.shape}")

    pattern = cfa_pattern.upper().strip()
    if len(pattern) != 4 or set(pattern) - set("RGB"):
        raise ValueError(f"Invalid 2x2 Bayer CFA pattern: {cfa_pattern!r}")

    slices_2x2 = (
        (slice(0, None, 2), slice(0, None, 2)),
        (slice(0, None, 2), slice(1, None, 2)),
        (slice(1, None, 2), slice(0, None, 2)),
        (slice(1, None, 2), slice(1, None, 2)),
    )
    planes: dict[str, list[np.ndarray]] = {"R": [], "G": [], "B": []}
    for letter, slc in zip(pattern, slices_2x2):
        planes[letter].append(mosaic[slc])
    return planes


def extract_rgn_bands(
    mosaic: np.ndarray,
    *,
    camera_config: dict[str, Any] | None = None,
    survey_metadata: dict[str, Any] | None = None,
    keep_half_resolution: bool | None = None,
) -> dict[str, Any]:
    """Extract verified spectral bands (Red 660nm, Green 550nm, NIR 850nm) from a Bayer mosaic.

    Args:
        mosaic: 2D numpy array of shape (H, W) with even dimensions.
        camera_config: Optional dictionary loaded from configs/camera.yaml.
        survey_metadata: Optional dictionary loaded from survey metadata.json.
        keep_half_resolution: If True (default), retain native 2x2 Bayer plane resolution
            (H/2, W/2). If False, resize each band back to full sensor dimensions (H, W)
            using bilinear interpolation.

    Returns:
        Dictionary containing:
            - "bands": dict mapping band name ("red", "green", "nir") -> 2D float32 ndarray
            - "metadata": band mapping, wavelengths, shapes, and per-band statistics
    """
    cam_cfg = (camera_config or {}).get("camera", {}) if camera_config else {}
    bands_cfg = (camera_config or {}).get("bands", {}) if camera_config else {}
    survey_cam = (survey_metadata or {}).get("camera", {}) if survey_metadata else {}

    cam_filter = str(survey_cam.get("filter") or cam_cfg.get("filter") or "RGN").upper().strip()
    if cam_filter not in SUPPORTED_FILTERS:
        raise ValueError(
            f"Unsupported or unconfirmed camera filter {cam_filter!r}. "
            f"Supported filters: {sorted(SUPPORTED_FILTERS)}"
        )

    cfa_pattern = str(cam_cfg.get("cfa_pattern", "RGGB")).upper().strip()
    if keep_half_resolution is None:
        keep_half_resolution = bool(cam_cfg.get("keep_half_resolution", True))

    planes = _split_cfa_positions(mosaic, cfa_pattern=cfa_pattern)
    filter_spec = SUPPORTED_FILTERS[cam_filter]
    survey_bands_meta = survey_cam.get("bands") if isinstance(survey_cam.get("bands"), dict) else {}

    full_height, full_width = int(mosaic.shape[0]), int(mosaic.shape[1])
    extracted_bands: dict[str, np.ndarray] = {}
    band_info: dict[str, dict[str, Any]] = {}

    for band_name, spec in filter_spec.items():
        # Check if band is explicitly disabled in camera.yaml
        cfg_entry = bands_cfg.get(band_name) if isinstance(bands_cfg, dict) else None
        if isinstance(cfg_entry, dict) and cfg_entry.get("enabled") is False:
            continue

        bayer_pos = str(
            (cfg_entry or {}).get("bayer_position") or spec["bayer_position"]
        ).upper()
        samples = planes.get(bayer_pos, [])
        if not samples:
            raise ValueError(f"Bayer position {bayer_pos!r} for band {band_name!r} not found in {cfa_pattern}")

        if len(samples) == 1:
            plane = samples[0].astype(np.float32)
        else:
            plane = np.mean([s.astype(np.float32) for s in samples], axis=0, dtype=np.float32)

        if not keep_half_resolution:
            plane = cv2.resize(
                plane,
                (full_width, full_height),
                interpolation=cv2.INTER_LINEAR,
            ).astype(np.float32)

        if not np.all(np.isfinite(plane)):
            raise ValueError(f"Extracted band {band_name!r} contains NaN or Inf values")

        wavelength = (
            survey_bands_meta.get(band_name)
            or (cfg_entry or {}).get("wavelength_nm")
            or spec["wavelength_nm"]
        )

        extracted_bands[band_name] = plane
        band_info[band_name] = {
            "wavelength_nm": int(wavelength) if wavelength is not None else None,
            "bayer_position": bayer_pos if len(samples) == 1 else "G1+G2_avg",
            "shape": [int(plane.shape[0]), int(plane.shape[1])],
            "dtype": str(plane.dtype),
            "min": round(float(plane.min()), 2),
            "max": round(float(plane.max()), 2),
            "mean": round(float(plane.mean()), 2),
            "std": round(float(plane.std()), 2),
        }

    # Verify all extracted bands share identical dimensions
    shapes = {tuple(info["shape"]) for info in band_info.values()}
    if len(shapes) > 1:
        raise ValueError(f"Inconsistent band shapes extracted: {shapes}")

    return {
        "bands": extracted_bands,
        "metadata": {
            "camera_model": survey_cam.get("model") or cam_cfg.get("model") or "MAPIR Survey3W",
            "filter": cam_filter,
            "cfa_pattern": cfa_pattern,
            "source_shape": [full_height, full_width],
            "keep_half_resolution": keep_half_resolution,
            "band_count": len(extracted_bands),
            "bands": band_info,
        },
    }


def save_extracted_bands(
    extraction_result: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Save extracted spectral bands as single-band TIFF files (red.tif, green.tif, nir.tif)
    along with band_metadata.json.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    bands: dict[str, np.ndarray] = extraction_result["bands"]
    meta: dict[str, Any] = dict(extraction_result["metadata"])
    saved_files: dict[str, str] = {}

    for band_name, array in bands.items():
        tif_path = out_path / f"{band_name}.tif"
        height, width = array.shape
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", NotGeoreferencedWarning)
            with rasterio.open(
                tif_path,
                "w",
                driver="GTiff",
                height=height,
                width=width,
                count=1,
                dtype=np.float32,
                crs=None,
                transform=Affine.identity(),
            ) as dst:
                dst.write(array.astype(np.float32), 1)
                band_meta = meta["bands"].get(band_name, {})
                dst.set_band_description(1, f"{band_name.upper()} ({band_meta.get('wavelength_nm')}nm)")
                dst.update_tags(
                    band_name=band_name,
                    wavelength_nm=str(band_meta.get("wavelength_nm", "")),
                    bayer_position=str(band_meta.get("bayer_position", "")),
                    camera_filter=str(meta.get("filter", "")),
                )
        saved_files[band_name] = str(tif_path)

    meta["output_dir"] = str(out_path.resolve())
    meta["files"] = saved_files

    meta_json_path = out_path / "band_metadata.json"
    meta_json_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta


def extract_bands_from_raw(
    raw_path: str | Path,
    output_dir: str | Path,
    *,
    camera_config: dict[str, Any] | None = None,
    survey_metadata: dict[str, Any] | None = None,
    keep_half_resolution: bool | None = None,
) -> dict[str, Any]:
    """Read a RAW file, extract confirmed spectral bands, and save intermediate .tif files."""
    mosaic, raw_meta = read_raw(raw_path, survey_metadata=survey_metadata)
    extraction = extract_rgn_bands(
        mosaic,
        camera_config=camera_config,
        survey_metadata=survey_metadata,
        keep_half_resolution=keep_half_resolution,
    )
    extraction["metadata"]["source_file"] = raw_meta.get("source")
    extraction["metadata"]["decoder"] = raw_meta.get("decoder")
    saved_meta = save_extracted_bands(extraction, output_dir=output_dir)
    return saved_meta
