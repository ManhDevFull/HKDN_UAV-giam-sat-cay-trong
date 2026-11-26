"""Validate a survey folder delivered by Group A before running the Group B pipeline."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image

from agriscan.io.metadata_reader import read_metadata, validate_metadata

MAPIR_RAW12_EXPECTED_BYTES = 4000 * 3000 * 3 // 2  # 18,000,000 bytes


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _inspect_jpg_exif(jpg_path: Path) -> dict[str, Any]:
    """Extract basic dimensions, camera Make/Model, DateTime, and GPS presence from a JPG."""
    info: dict[str, Any] = {
        "file": jpg_path.name,
        "width": None,
        "height": None,
        "make": None,
        "model": None,
        "datetime": None,
        "has_gps": False,
    }
    with Image.open(jpg_path) as img:
        info["width"], info["height"] = img.size
        exif_raw = img.getexif()
        if exif_raw:
            tags = {ExifTags.TAGS.get(k, k): v for k, v in exif_raw.items()}
            info["make"] = tags.get("Make")
            info["model"] = tags.get("Model")
            info["datetime"] = tags.get("DateTimeOriginal") or tags.get("DateTime")
            info["has_gps"] = "GPSInfo" in tags and bool(tags["GPSInfo"])
    return info


def validate_survey_folder(
    survey_dir: str | Path,
    *,
    expected_raw_bytes: int = MAPIR_RAW12_EXPECTED_BYTES,
    verify_checksums: bool = True,
) -> dict[str, Any]:
    """Run the 10-step input validation checklist on a survey directory.

    Checklist:
        1. Survey directory and required subdirectories exist.
        2. metadata.json exists and conforms to schema.
        3. survey_id and plot_id are valid.
        4. Camera model and filter are confirmed.
        5. RAW files exist in raw/.
        6. Calibration target images (before/after) exist.
        7. Manifest / SHA-256 checksums match (if logs/image_manifest.csv exists).
        8. EXIF / GPS metadata on companion JPGs.
        9. File sizes and image dimensions are valid.
        10. Duplicate or corrupted (0-byte / truncated) files are flagged.
    """
    root = Path(survey_dir)
    errors: list[str] = []
    warnings: list[str] = []

    report: dict[str, Any] = {
        "survey_dir": str(root.resolve()) if root.exists() else str(root),
        "is_valid": False,
        "status": "failed",
        "survey_id": None,
        "plot_id": None,
        "camera": None,
        "counts": {
            "total_files_in_raw_dir": 0,
            "raw_count": 0,
            "jpg_count": 0,
            "metadata_image_count": None,
        },
        "calibration": {
            "before_path": None,
            "before_exists": False,
            "after_path": None,
            "after_exists": False,
        },
        "corrupted_files": [],
        "duplicate_files": [],
        "exif_summary": {
            "checked_jpgs": 0,
            "with_exif_model": 0,
            "with_gps": 0,
            "models_found": [],
            "dimensions_found": [],
        },
        "manifest_verified": None,
        "errors": errors,
        "warnings": warnings,
    }

    # 1. Directory existence
    if not root.exists() or not root.is_dir():
        errors.append(f"Survey directory does not exist: {root}")
        return report

    metadata_path = root / "metadata.json"
    raw_dir = root / "raw"

    if not metadata_path.exists():
        errors.append(f"Missing required metadata file: {metadata_path}")
    if not raw_dir.exists() or not raw_dir.is_dir():
        errors.append(f"Missing required 'raw/' directory: {raw_dir}")

    # 2, 3, 4. Metadata schema, survey_id/plot_id, camera/filter
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = read_metadata(metadata_path, strict=False)
            _, meta_errors, meta_warnings = validate_metadata(metadata)
            errors.extend(meta_errors)
            warnings.extend(meta_warnings)
            report["survey_id"] = metadata.get("survey_id")
            report["plot_id"] = metadata.get("plot_id")
            report["camera"] = metadata.get("camera")
            report["counts"]["metadata_image_count"] = metadata.get("image_count")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"Failed to read metadata.json: {exc}")

    # 6. Calibration target files check
    cal_target = metadata.get("calibration_target") if isinstance(metadata, dict) else None
    if isinstance(cal_target, dict):
        before_rel = cal_target.get("before")
        after_rel = cal_target.get("after")
        if before_rel:
            before_path = root / before_rel
            report["calibration"]["before_path"] = str(before_rel)
            report["calibration"]["before_exists"] = before_path.exists()
            if not before_path.exists():
                warnings.append(f"Calibration 'before' file not found on disk: {before_rel}")
        if after_rel:
            after_path = root / after_rel
            report["calibration"]["after_path"] = str(after_rel)
            report["calibration"]["after_exists"] = after_path.exists()
            if not after_path.exists():
                warnings.append(f"Calibration 'after' file not found on disk: {after_rel}")

    # 5, 8, 9, 10. Scan raw/ directory
    if raw_dir.exists() and raw_dir.is_dir():
        all_files = sorted([p for p in raw_dir.iterdir() if p.is_file()])
        raw_files = [p for p in all_files if p.suffix.upper() == ".RAW"]
        jpg_files = [p for p in all_files if p.suffix.upper() in {".JPG", ".JPEG"}]

        report["counts"]["total_files_in_raw_dir"] = len(all_files)
        report["counts"]["raw_count"] = len(raw_files)
        report["counts"]["jpg_count"] = len(jpg_files)

        if len(raw_files) == 0:
            errors.append("No .RAW files found in 'raw/' directory")

        meta_count = report["counts"]["metadata_image_count"]
        if isinstance(meta_count, int) and meta_count not in (len(raw_files), len(all_files)):
            warnings.append(
                f"metadata.image_count ({meta_count}) does not match RAW count ({len(raw_files)}) "
                f"or total file count ({len(all_files)}) in 'raw/'"
            )

        if len(raw_files) != len(jpg_files):
            warnings.append(
                f"Unequal number of RAW ({len(raw_files)}) and JPG ({len(jpg_files)}) files in 'raw/'"
            )

        # Check RAW file sizes & duplicates
        seen_hashes: dict[str, str] = {}
        for raw_file in raw_files:
            size = raw_file.stat().st_size
            if size == 0:
                report["corrupted_files"].append(raw_file.name)
                errors.append(f"Empty (0-byte) RAW file: {raw_file.name}")
            elif expected_raw_bytes and size != expected_raw_bytes:
                report["corrupted_files"].append(raw_file.name)
                errors.append(
                    f"Unexpected RAW file size for {raw_file.name}: {size} bytes "
                    f"(expected {expected_raw_bytes} bytes)"
                )
            if verify_checksums and size > 0:
                digest = _sha256_file(raw_file)
                if digest in seen_hashes:
                    dup_pair = f"{raw_file.name} == {seen_hashes[digest]}"
                    report["duplicate_files"].append(dup_pair)
                    warnings.append(f"Duplicate RAW file content detected: {dup_pair}")
                else:
                    seen_hashes[digest] = raw_file.name

        # Check JPG files and EXIF/GPS
        models_found: set[str] = set()
        dims_found: set[str] = set()
        with_model = 0
        with_gps = 0

        for jpg_file in jpg_files:
            size = jpg_file.stat().st_size
            if size == 0:
                report["corrupted_files"].append(jpg_file.name)
                errors.append(f"Empty (0-byte) JPG file: {jpg_file.name}")
                continue
            try:
                exif_info = _inspect_jpg_exif(jpg_file)
                if exif_info["model"]:
                    with_model += 1
                    models_found.add(str(exif_info["model"]).strip())
                if exif_info["has_gps"]:
                    with_gps += 1
                if exif_info["width"] and exif_info["height"]:
                    dims_found.add(f"{exif_info['width']}x{exif_info['height']}")
            except (OSError, ValueError, TypeError) as exc:
                report["corrupted_files"].append(jpg_file.name)
                errors.append(f"Corrupted JPG file {jpg_file.name}: {exc}")

        report["exif_summary"] = {
            "checked_jpgs": len(jpg_files),
            "with_exif_model": with_model,
            "with_gps": with_gps,
            "models_found": sorted(models_found),
            "dimensions_found": sorted(dims_found),
        }

    # 7. Check manifest if present
    manifest_path = root / "logs" / "image_manifest.csv"
    if manifest_path.exists():
        manifest_ok = True
        with manifest_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stored_name = row.get("stored_name", "")
                expected_sha = row.get("sha256", "")
                candidate = raw_dir / stored_name
                if not candidate.exists():
                    manifest_ok = False
                    errors.append(f"File listed in manifest is missing: {stored_name}")
                elif expected_sha and verify_checksums:
                    actual_sha = _sha256_file(candidate)
                    if actual_sha.lower() != expected_sha.lower():
                        manifest_ok = False
                        errors.append(f"SHA-256 mismatch for {stored_name}")
        report["manifest_verified"] = manifest_ok

    report["is_valid"] = len(errors) == 0
    if len(errors) > 0:
        report["status"] = "failed"
    elif len(warnings) > 0:
        report["status"] = "needs_review"
    else:
        report["status"] = "valid"

    return report
