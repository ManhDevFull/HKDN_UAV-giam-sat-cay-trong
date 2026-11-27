"""Quality gates for quantitative, georeferenced R/G/NIR mosaics.

A raster's bounding rectangle is not the surveyed area. Coverage is assessed
against an optional GeoJSON AOI; without one, holes are reported as unverified.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom


class MosaicQualityError(ValueError):
    """A mosaic must not enter the index/alert pipeline."""


def _aoi_geometries(path: Path, target_crs: Any) -> list[dict]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    source_crs = document.get("crs", {}).get("properties", {}).get("name", "EPSG:4326")
    kind = document.get("type")
    if kind == "FeatureCollection":
        geometries = [feature.get("geometry") for feature in document.get("features", [])]
    elif kind == "Feature":
        geometries = [document.get("geometry")]
    else:
        geometries = [document]
    result = []
    for geometry in geometries:
        if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise MosaicQualityError("AOI phải là GeoJSON Polygon/MultiPolygon có tọa độ hợp lệ.")
        result.append(transform_geom(source_crs, target_crs, geometry))
    if not result:
        raise MosaicQualityError("AOI không có polygon.")
    return result


def assess_mosaic(
    path: str | Path,
    *,
    boundary_path: str | Path | None = None,
    min_coverage: float = 0.9,
    require_uint16: bool = False,
) -> dict[str, Any]:
    """Check projected metric geometry, 3 spectral bands, masks and AOI coverage.

    Values are read by raster blocks to avoid loading the full orthomosaic into
    RAM. RGB JPEG/uint8 input cannot be passed off as quantitative band data.
    """
    path = Path(path)
    if not 0 < float(min_coverage) <= 1:
        raise ValueError("min_coverage phải thuộc (0, 1].")
    try:
        source = rasterio.open(path)
    except rasterio.errors.RasterioIOError as exc:
        raise MosaicQualityError(f"Không mở được orthomosaic: {path}") from exc
    with source:
        if source.count < 3 or source.count > 4:
            raise MosaicQualityError("Orthomosaic phải có 3 băng R/G/NIR và có thể thêm alpha.")
        if source.crs is None or not source.crs.is_projected:
            raise MosaicQualityError("Orthomosaic thiếu CRS chiếu thực; không dùng bản đồ giả tọa độ.")
        if source.crs.linear_units not in ("metre", "meter", "metres", "meters"):
            raise MosaicQualityError("Orthomosaic phải dùng CRS chiếu theo mét để chia ô chính xác.")
        transform = source.transform
        if (not all(math.isfinite(value) for value in transform) or
                abs(transform.a * transform.e - transform.b * transform.d) < 1e-15 or
                transform.is_identity):
            raise MosaicQualityError("Geotransform của orthomosaic không hợp lệ.")
        if not all(math.isfinite(v) for v in source.bounds):
            raise MosaicQualityError("Giới hạn tọa độ orthomosaic không hợp lệ.")
        dtypes = source.dtypes[:3]
        if any(np.dtype(dtype).kind not in "uif" or np.dtype(dtype).itemsize < 2 for dtype in dtypes):
            raise MosaicQualityError("Không dùng ảnh 8 bit/gamma làm băng phổ để tính NDVI.")
        if require_uint16 and any(dtype != "uint16" for dtype in dtypes):
            raise MosaicQualityError("ODM làm thay đổi kiểu dữ liệu; cần giữ 3 băng uint16.")
        geometries = _aoi_geometries(Path(boundary_path), source.crs) if boundary_path else None
        valid_count = aoi_count = aoi_valid_count = 0
        minima = np.full(3, np.inf)
        maxima = np.full(3, -np.inf)
        for _, window in source.block_windows(1):
            values = source.read((1, 2, 3), window=window)
            valid = np.all(source.read_masks((1, 2, 3), window=window) > 0, axis=0)
            valid &= np.all(np.isfinite(values), axis=0)
            if source.count == 4:
                valid &= source.read(4, window=window) > 0
            valid_count += int(np.count_nonzero(valid))
            if np.any(valid):
                for index in range(3):
                    minima[index] = min(minima[index], float(np.min(values[index][valid])))
                    maxima[index] = max(maxima[index], float(np.max(values[index][valid])))
            if geometries:
                inside = geometry_mask(geometries, values.shape[1:], source.window_transform(window), invert=True)
                aoi_count += int(np.count_nonzero(inside))
                aoi_valid_count += int(np.count_nonzero(inside & valid))
        if valid_count == 0:
            raise MosaicQualityError("Orthomosaic rỗng hoặc toàn bộ pixel là NoData.")
        if any(not math.isfinite(v) or hi <= lo for lo, hi, v in zip(minima, maxima, maxima)):
            raise MosaicQualityError("Có băng phổ không có biến thiên; kiểm tra thứ tự băng và ảnh nguồn.")
        report: dict[str, Any] = {
            "path": str(path), "crs": source.crs.to_string(),
            "width": source.width, "height": source.height,
            "bands": ["red", "green", "nir"], "dtypes": list(dtypes),
            "pixel_size_m": [float(math.hypot(transform.a, transform.d)), float(math.hypot(transform.b, transform.e))],
            "bounds": list(source.bounds), "valid_pixels": valid_count,
            "valid_fraction_bbox": valid_count / (source.width * source.height),
            "band_min": minima.tolist(), "band_max": maxima.tolist(),
            "aoi_coverage": None, "holes_verified": False,
            "warnings": [],
        }
        if geometries:
            # Rasterize the whole AOI extent at this raster's pixel size so an
            # AOI partly outside the raster cannot receive a false 100% score.
            from shapely.geometry import shape
            from shapely.ops import unary_union
            from rasterio.windows import from_bounds, Window
            shape_union = unary_union([shape(geom) for geom in geometries])
            if not shape_union.is_valid or shape_union.is_empty:
                raise MosaicQualityError("AOI có hình học không hợp lệ.")
            if transform.b != 0 or transform.d != 0:
                raise MosaicQualityError("AOI coverage yêu cầu raster north-up; hãy warp raster trước.")
            whole_window = from_bounds(*shape_union.bounds, transform=transform)
            left = math.floor(whole_window.col_off)
            top = math.floor(whole_window.row_off)
            right = math.ceil(whole_window.col_off + whole_window.width)
            bottom = math.ceil(whole_window.row_off + whole_window.height)
            total_aoi = 0
            # Bounded-size tiles also account for pixels beyond dataset bounds.
            for y in range(top, bottom, 1024):
                for x in range(left, right, 1024):
                    window = Window(x, y, min(1024, right - x), min(1024, bottom - y))
                    inside = geometry_mask(geometries, (int(window.height), int(window.width)),
                                           source.window_transform(window), invert=True)
                    total_aoi += int(np.count_nonzero(inside))
            if total_aoi == 0:
                raise MosaicQualityError("AOI không có pixel ở độ phân giải orthomosaic.")
            coverage = aoi_valid_count / total_aoi
            report.update(aoi_coverage=coverage, holes_verified=True, aoi_pixels=total_aoi)
            if coverage < min_coverage:
                raise MosaicQualityError(
                    f"Orthomosaic chỉ phủ {coverage:.1%} AOI, yêu cầu {min_coverage:.1%}; kiểm tra overlap/ảnh thiếu.")
        else:
            report["warnings"].append("Chưa có AOI: chưa kiểm chứng vùng khảo sát bị hổng hay thiếu biên.")
        return report


def check_reconstruction(
    project_dir: str | Path,
    image_names: Iterable[str],
    *,
    min_used_ratio: float = 0.9,
) -> dict[str, Any]:
    """Reject disconnected or mostly missing OpenSfM reconstructions."""
    names = set(image_names)
    if not names:
        raise MosaicQualityError("Không có danh sách ảnh nguồn để kiểm tra reconstruction.")
    path = Path(project_dir) / "opensfm" / "reconstruction.json"
    if not path.is_file():
        raise MosaicQualityError("ODM không tạo reconstruction.json; không kiểm chứng được ảnh đã ghép.")
    try:
        reconstructions = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise MosaicQualityError("reconstruction.json không đọc được.") from exc
    if not isinstance(reconstructions, list):
        raise MosaicQualityError("reconstruction.json sai định dạng OpenSfM.")
    components = [item for item in reconstructions if isinstance(item, dict) and item.get("shots")]
    if len(components) != 1:
        raise MosaicQualityError(
            f"Có {len(components)} khối reconstruction; ảnh không đủ overlap/đang bị tách khối.")
    used = names.intersection(components[0]["shots"])
    ratio = len(used) / len(names)
    report = {"input_images": len(names), "used_images": len(used), "used_image_ratio": ratio,
              "components": 1, "unused_images": sorted(names - used)}
    if len(used) < 3 or ratio < float(min_used_ratio):
        raise MosaicQualityError(
            f"ODM chỉ ghép {len(used)}/{len(names)} ảnh ({ratio:.1%}); yêu cầu {float(min_used_ratio):.1%}. "
            "Kiểm tra overlap, ảnh mờ, ảnh khác buổi; không phát cảnh báo từ bản ghép thiếu ảnh.")
    return report


def inspect_mosaic(
    path: str | Path,
    *,
    boundary_path: str | Path | None = None,
    min_coverage: float = 0.9,
    require_uint16: bool = False,
) -> dict[str, Any]:
    """Public quality gate for an already georeferenced quantitative mosaic."""
    return assess_mosaic(path, boundary_path=boundary_path, min_coverage=min_coverage,
                         require_uint16=require_uint16)
