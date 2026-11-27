"""Run a pinned OpenDroneMap container on linear R/G/NIR uint16 TIFFs.

Official flag contract: https://github.com/OpenDroneMap/ODM/tree/v3.5.6
The deprecated local seam-leveling flag is deliberately absent. ODM 3.5.6
uses tone mapping ``none`` internally; global normalization is disabled here.
Feature detection may normalize temporary images, while undistorted TIFFs used
for texturing keep their original 16-bit numeric scale.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
from uuid import uuid4
import warnings

import numpy as np
from PIL import Image
import rasterio

from .mosaic_quality import MosaicQualityError, assess_mosaic, check_reconstruction

DEFAULT_IMAGE = "opendronemap/odm:3.5.6"


class ODMError(RuntimeError):
    """Actionable ODM failure with a persistent log file."""

    def __init__(self, message: str, *, code: str = "odm_failed", log_path: Path | None = None):
        self.code = code
        self.log_path = log_path
        if log_path:
            message += f" Log: {log_path}"
        super().__init__(message)


def _settings(config: dict) -> dict:
    value = config.get("odm", config)
    if not isinstance(value, dict):
        raise ValueError("Cấu hình odm phải là mapping.")
    return value


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _input_images(image_dir: Path, min_images: int = 3) -> list[Path]:
    if not image_dir.is_dir():
        raise ODMError(f"Không có thư mục ảnh ODM: {image_dir}", code="input_missing")
    candidates = sorted(path for path in image_dir.iterdir()
                        if path.is_file() and path.suffix.lower() in (".tif", ".tiff"))
    if len(candidates) < min_images:
        raise ODMError(f"Cần ít nhất {min_images} TIFF R/G/NIR có overlap và GPS để ghép ODM.", code="insufficient_images")
    hashes: dict[str, str] = {}
    dimensions = set()
    for path in candidates:
        if re.search(r"\s", path.name):
            raise ODMError("Tên TIFF đưa vào ODM không được chứa khoảng trắng (geo.txt).", code="input_name")
        try:
            # Prepared camera TIFFs intentionally have no map transform: the
            # camera centres are supplied separately in geo.txt. Suppress only
            # this expected warning; final orthomosaics still require real CRS.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", rasterio.errors.NotGeoreferencedWarning)
                dataset = rasterio.open(path)
            with dataset as image:
                if image.count != 3 or image.dtypes != ("uint16", "uint16", "uint16"):
                    raise ODMError(f"{path.name}: ODM cần 3 băng uint16 tuyến tính R/G/NIR; không dùng preview/JPG.",
                                   code="spectral_input")
                dimensions.add((image.width, image.height))
                if min(image.width, image.height) < 32:
                    raise ODMError(f"{path.name}: ảnh quá nhỏ cho SfM.", code="spectral_input")
                # Quickly reject unusable frames; texture failure later receives
                # a specific overlap/features diagnosis rather than fake output.
                sample = image.read(out_shape=(3, min(256, image.height), min(256, image.width)))
                if np.max(sample) == np.min(sample):
                    raise ODMError(f"{path.name}: ảnh không có tín hiệu/texture.", code="low_signal")
        except rasterio.errors.RasterioIOError as exc:
            raise ODMError(f"Không đọc được TIFF: {path.name}", code="corrupt_image") from exc
        digest = _hash_file(path)
        if digest in hashes:
            raise ODMError(f"Ảnh trùng hệt nhau: {hashes[digest]}, {path.name}; không thể tính thành hai góc chụp.",
                           code="duplicate_image")
        hashes[digest] = path.name
    if len(dimensions) != 1:
        raise ODMError("Các TIFF R/G/NIR phải cùng kích thước và cùng camera.", code="camera_mismatch")
    return candidates


def _gps_from_exif(path: Path) -> dict | None:
    try:
        with Image.open(path) as image:
            gps = image.getexif().get_ifd(34853)
        if not gps or not all(key in gps for key in (1, 2, 3, 4, 6)):
            return None
        def coordinate(value):
            return float(value[0]) + float(value[1]) / 60 + float(value[2]) / 3600
        latitude, longitude = coordinate(gps[2]), coordinate(gps[4])
        if str(gps[1]).upper().startswith("S"):
            latitude *= -1
        if str(gps[3]).upper().startswith("W"):
            longitude *= -1
        altitude = float(gps[6])
        reference = gps.get(5, 0)
        if reference == 1 or reference == b"\x01":
            altitude *= -1
        return {"longitude": longitude, "latitude": latitude, "altitude": altitude}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ZeroDivisionError):
        return None


def _write_positions(images: list[Path], supplied: dict | None, destination: Path) -> None:
    lines = ["EPSG:4326"]
    unique = set()
    for path in images:
        position = (supplied or {}).get(path.name) or _gps_from_exif(path)
        if not isinstance(position, dict):
            raise ODMError(f"{path.name}: thiếu GPS camera. Cần GPS của nhóm A hoặc GCP; không tự bịa tọa độ.",
                           code="gps_missing")
        try:
            longitude = float(position.get("longitude", position.get("lon")))
            latitude = float(position.get("latitude", position.get("lat")))
            altitude = float(position.get("altitude", position.get("alt")))
        except (TypeError, ValueError) as exc:
            raise ODMError(f"{path.name}: GPS cần longitude, latitude, altitude theo WGS84.", code="gps_invalid") from exc
        if (not all(math.isfinite(v) for v in (longitude, latitude, altitude)) or
                not -180 <= longitude <= 180 or not -90 <= latitude <= 90 or
                longitude == latitude == 0):
            raise ODMError(f"{path.name}: GPS ngoài giới hạn hoặc bằng (0, 0).", code="gps_invalid")
        unique.add((round(longitude, 9), round(latitude, 9)))
        values = [path.name, f"{longitude:.10f}", f"{latitude:.10f}", f"{altitude:.4f}"]
        angles = [position.get(key) for key in ("yaw", "pitch", "roll")]
        if all(angle is not None for angle in angles):
            numeric = [float(angle) for angle in angles]
            if not all(math.isfinite(angle) for angle in numeric):
                raise ODMError(f"{path.name}: góc camera không hợp lệ.", code="gps_invalid")
            values.extend(str(angle) for angle in numeric)
        lines.append(" ".join(values))
    if len(unique) < 3:
        raise ODMError("Cần ít nhất 3 vị trí camera khác nhau để ghép có tọa độ.", code="gps_degenerate")
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _runtime_check(runtime: str) -> None:
    if not shutil.which(runtime):
        raise ODMError("Chưa có Docker. Cài Docker Engine, khởi động daemon và cho tài khoản quyền chạy docker.",
                       code="docker_missing")
    try:
        result = subprocess.run([runtime, "info", "--format", "{{.ServerVersion}}"],
                                capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ODMError("Không kết nối được Docker daemon; kiểm tra docker info.", code="docker_daemon") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout)[-1500:].strip()
        raise ODMError(f"Docker daemon chưa chạy hoặc tài khoản chưa có quyền: {detail}", code="docker_daemon")


def _classify_failure(log: str, returncode: int) -> tuple[str, str]:
    value = log.lower()
    if returncode == 137 or any(token in value for token in ("out of memory", "oom-kill", "bad_alloc", "cannot allocate memory", "killed signal")):
        return "memory", "ODM thiếu RAM. Giảm max_concurrency/pc_quality hoặc chia bộ ảnh có overlap; xem dung lượng RAM Docker."
    if any(token in value for token in ("permission denied", "cannot connect to the docker daemon", "is the docker daemon running")):
        return "docker_daemon", "Docker thiếu quyền hoặc daemon ngừng chạy; kiểm tra docker info."
    if any(token in value for token in ("manifest unknown", "pull access denied", "no such image", "failed to resolve reference")):
        return "docker_image", "Không tải được ảnh Docker ODM đã ghim phiên bản; kiểm tra kết nối và docker pull."
    if any(token in value for token in ("not enough images", "not enough photos", "no reconstruction", "reconstruction failed", "not enough tracks", "no common tracks", "cannot reconstruct", "0 partial reconstructions", "could not find a valid initial", "could not reconstruct", "no features", "zero matches")):
        return "features", "ODM không khôi phục được camera: kiểm tra overlap, ảnh mờ, ảnh khác khu vực/buổi chụp."
    if any(token in value for token in ("no space left", "disk quota exceeded")):
        return "disk", "Hết dung lượng đĩa cho ODM; giải phóng dung lượng rồi chạy lại."
    if any(token in value for token in ("band", "radiometric", "image must be rgb")):
        return "spectral", "ODM không đọc được băng phổ; kiểm tra TIFF R/G/NIR uint16 và metadata camera."
    return "odm_failed", "ODM ghép thất bại; đọc cuối log để kiểm tra dữ liệu và tham số."


def _bounded_number(settings: dict, key: str, default: float, low: float, high: float, *, integer: bool = False):
    value = float(settings.get(key, default))
    if not math.isfinite(value) or not low <= value <= high or integer and value != int(value):
        raise ValueError(f"odm.{key} phải thuộc [{low}, {high}].")
    return int(value) if integer else value


def _command(runtime: str, image: str, workspace: Path, container: str, settings: dict, retry_kind: str | None) -> list[str]:
    concurrency = _bounded_number(settings, "max_concurrency", min(4, os.cpu_count() or 1), 1, 64, integer=True)
    feature_quality = str(settings.get("feature_quality", "high"))
    pc_quality = str(settings.get("pc_quality", "medium"))
    qualities = ("ultra", "high", "medium", "low", "lowest")
    if feature_quality not in qualities or pc_quality not in qualities:
        raise ValueError("odm.feature_quality/pc_quality không hợp lệ.")
    min_features = _bounded_number(settings, "min_num_features", 10000, 1000, 100000, integer=True)
    if retry_kind == "memory":
        concurrency, feature_quality, pc_quality = 1, "medium", "low"
    elif retry_kind == "features":
        min_features, feature_quality = max(20000, min_features), "high"
    args = [runtime, "run", "--rm", "--name", container,
            "--user", f"{os.getuid()}:{os.getgid()}", "--network", "none",
            "--cpus", str(concurrency), "--volume", f"{workspace}:/datasets",
            "--workdir", "/datasets/survey",
            "--security-opt", "no-new-privileges", "--cap-drop", "ALL"]
    if settings.get("memory_gb") is not None:
        memory = _bounded_number(settings, "memory_gb", 16, 2, 2048)
        args.extend(["--memory", f"{memory:g}g"])
    args.extend([image, "--project-path", "/datasets", "survey", "--geo", "/datasets/survey/geo.txt",
                 "--radiometric-calibration", "none", "--texturing-skip-global-seam-leveling",
                 "--skip-band-alignment", "--skip-3dmodel", "--sfm-no-partial", "--skip-report",
                 "--max-concurrency", str(concurrency), "--feature-quality", feature_quality,
                 "--pc-quality", pc_quality, "--min-num-features", str(min_features),
                 "--orthophoto-resolution", str(_bounded_number(settings, "orthophoto_resolution", settings.get("orthophoto_resolution_cm", 5), 0.1, 1000)),
                 "--orthophoto-compression", "DEFLATE"])
    # These alternatives change matching, not radiometric scale. Never retry an
    # unknown failure or loop indefinitely on insufficient overlap.
    if retry_kind == "features":
        args.extend(["--matcher-neighbors", "8", "--feature-type", "sift"])
    if settings.get("fast_orthophoto", False):
        args.append("--fast-orthophoto")
    if retry_kind:
        args.append("--rerun-all")
    return args


def _canonical_copy(source_path: Path, destination: Path, scale: float, image: str = DEFAULT_IMAGE) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp.tif")
    try:
        with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), rasterio.open(source_path) as source:
            profile = source.profile.copy()
            profile.update(count=3, driver="GTiff", compress="deflate", predictor=2,
                           tiled=True, blockxsize=256, blockysize=256, BIGTIFF="IF_SAFER")
            # ODM generally returns alpha. The canonical product keeps three
            # spectral bands and writes alpha validity into an internal mask.
            profile.pop("photometric", None)
            profile.pop("nodata", None)
            with rasterio.open(temporary, "w", **profile) as target:
                for _, window in source.block_windows(1):
                    values = source.read((1, 2, 3), window=window)
                    valid = np.all(source.read_masks((1, 2, 3), window=window) > 0, axis=0)
                    valid &= np.all(np.isfinite(values), axis=0)
                    if source.count == 4:
                        valid &= source.read(4, window=window) > 0
                    target.write(values, window=window)
                    target.write_mask(valid.astype("uint8") * 255, window=window)
                for index, name in enumerate(("red", "green", "nir"), start=1):
                    target.set_band_description(index, name)
                target.update_tags(band_order="red,green,nir", quantitative_source="linear_raw_uint16",
                                   radiometric_calibration="relative", value_scale=str(scale),
                                   absolute_reflectance_accuracy="not_verified", odm_image=image)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def run_odm(
    image_dir: Path,
    work_dir: Path,
    output_path: Path,
    *,
    config: dict,
    positions: dict | None = None,
    boundary_path: Path | None = None,
) -> dict[str, Any]:
    """Create and quality-check an orthomosaic, retaining bounded-attempt logs.

    The caller owns an isolated/staging ``work_dir``. An existing ODM workspace
    is rejected to avoid silently mixing prior images with a new survey. This
    function never fabricates geotags and never blends images as an ODM fallback.
    """
    image_dir, work_dir, output_path = Path(image_dir).resolve(), Path(work_dir).resolve(), Path(output_path).resolve()
    settings = _settings(config)
    runtime = str(settings.get("runtime", "docker"))
    image = str(settings.get("image", DEFAULT_IMAGE))
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@-]+", image):
        raise ValueError("Tên image Docker không hợp lệ.")
    if image.endswith(":latest") or ":" not in image:
        raise ValueError("Phải ghim phiên bản hoặc digest ảnh Docker ODM; không dùng latest.")
    minimum_images = _bounded_number(settings, "min_images", 3, 3, 1000000, integer=True)
    images = _input_images(image_dir, minimum_images)
    if any(output_path == path for path in images):
        raise ODMError("Đường dẫn orthomosaic không được ghi đè ảnh nguồn.", code="output_overlap")
    max_retries = _bounded_number(settings, "max_retries", 1, 0, 2, integer=True)
    timeout = _bounded_number(settings, "timeout_seconds", 7200, 1, 172800)
    min_used = _bounded_number(settings, "min_used_ratio", 0.9, 0.9, 1)
    min_coverage = _bounded_number(settings, "min_aoi_coverage", 0.9, 0.5, 1)
    scale = _bounded_number(settings, "common_scale", settings.get("value_scale", 16384), 1, 65535)
    project = work_dir / "survey"
    if project.exists():
        raise ODMError("ODM work_dir đã có dữ liệu; dùng thư mục staging mới để tránh lẫn kết quả cũ.", code="workspace_exists")
    if work_dir == image_dir or work_dir in image_dir.parents:
        raise ODMError("ODM work_dir không được chứa thư mục đầu vào.", code="workspace_overlap")
    _runtime_check(runtime)
    (project / "images").mkdir(parents=True)
    _write_positions(images, positions, project / "geo.txt")
    for path in images:
        shutil.copy2(path, project / "images" / path.name)
    attempts: list[dict] = []
    retry_kind = None
    for attempt in range(max_retries + 1):
        container = f"agriscan-odm-{uuid4().hex[:12]}"
        command = _command(runtime, image, work_dir, container, settings, retry_kind)
        log_path = work_dir / f"odm-attempt-{attempt + 1}.log"
        with log_path.open("w", encoding="utf-8") as log:
            log.write("Command: " + json.dumps(command, ensure_ascii=False) + "\n")
            log.flush()
            try:
                result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                        text=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired as exc:
                raise ODMError(f"ODM vượt quá {timeout:g} giây; đã dừng container. Kiểm tra log hoặc tăng timeout_seconds.",
                               code="timeout", log_path=log_path) from exc
            except OSError as exc:
                raise ODMError(f"Không khởi chạy được ODM: {exc}", code="docker_launch", log_path=log_path) from exc
            finally:
                # Killing only the docker client leaves computation running.
                # Remove the exact uniquely named container on timeout/cancel.
                try:
                    subprocess.run([runtime, "rm", "--force", container],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=15, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        attempts.append({"attempt": attempt + 1, "returncode": result.returncode,
                         "log": str(log_path), "retry_kind": retry_kind})
        if result.returncode == 0:
            break
        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-150000:]
        code, diagnosis = _classify_failure(log_tail, result.returncode)
        if attempt >= max_retries or code not in ("memory", "features") or retry_kind == code:
            raise ODMError(diagnosis, code=code, log_path=log_path)
        retry_kind = code
    native = project / "odm_orthophoto" / "odm_orthophoto.tif"
    try:
        reconstruction = check_reconstruction(project, [path.name for path in images], min_used_ratio=min_used)
        quality = assess_mosaic(native, boundary_path=boundary_path, min_coverage=min_coverage, require_uint16=True)
        _canonical_copy(native, output_path, scale, image)
    except MosaicQualityError as exc:
        raise ODMError(str(exc), code="quality_gate", log_path=log_path) from exc
    report = {"orthomosaic": str(output_path), "native_orthomosaic": str(native), "odm_image": image,
              "log_path": str(log_path), "attempts": attempts, "reconstruction": reconstruction,
              "quality": quality, "value_scale": scale,
              "radiometry": {"source": "linear_raw_uint16", "bands": ["red", "green", "nir"],
                             "radiometric_calibration": "none", "global_seam_leveling": False,
                             "local_seam_leveling_flag": "deprecated_in_ODM_3.5.6",
                             "absolute_reflectance_accuracy": "not_verified"}}
    quality_path = work_dir / "mosaic-quality.json"
    report["quality_path"] = str(quality_path)
    quality_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
