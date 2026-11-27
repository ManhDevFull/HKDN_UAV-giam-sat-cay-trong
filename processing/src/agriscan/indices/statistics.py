"""Windowed NDVI maps and globally anchored metric grid statistics."""

from __future__ import annotations

import csv
import json
import math
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from PIL import Image
from pyproj import CRS, Transformer
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds, transform as window_transform
from shapely import transform as coordinate_transform
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

from agriscan.indices.masking import MASK_NODATA, as_mask_raster, build_masks
from agriscan.indices.ndvi import NDVI_NODATA, calculate_ndvi
from agriscan.io.raster_io import output_profile


def _windows(width: int, height: int, size: int = 512):
    for row in range(0, height, size):
        for col in range(0, width, size):
            yield Window(col, row, min(size, width - col), min(size, height - row))


def _reproject(geometry: Any, transform: Any):
    return coordinate_transform(geometry, lambda xy: np.column_stack(transform(xy[:, 0], xy[:, 1])))


def _polygonal(geometry: Any):
    """Discard zero-area touch fragments after clipping multipart boundaries."""
    if geometry.geom_type == "Polygon":
        return geometry if geometry.area > 0 else Polygon()
    parts = [_polygonal(part) for part in getattr(geometry, "geoms", ())]
    parts = [part for part in parts if not part.is_empty]
    return unary_union(parts) if parts else Polygon()


def _metric_crs(dataset: Any) -> CRS:
    if dataset.crs is None:
        raise ValueError("Orthomosaic has no CRS; provide a genuinely georeferenced ODM raster")
    crs = CRS.from_user_input(dataset.crs)
    if not crs.is_projected or not all(abs(axis.unit_conversion_factor - 1.0) < 1e-9 for axis in crs.axis_info[:2]):
        raise ValueError("Metric grid requires a projected CRS in metres (for example the survey UTM CRS); reproject the mosaic first")
    t = dataset.transform
    if not np.isfinite(tuple(t)).all() or t.a <= 0 or t.e >= 0 or abs(t.b) > 1e-12 or abs(t.d) > 1e-12:
        raise ValueError("Orthomosaic must use a north-up, unrotated, finite transform")
    return crs


def _boundary(path: Path | None, raster_bounds: Any, crs: CRS):
    footprint = box(*raster_bounds)
    if path is None:
        return footprint
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    declared = (data.get("crs") or {}).get("properties", {}).get("name", "EPSG:4326")
    if declared not in ("EPSG:4326", "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326"):
        raise ValueError("Boundary GeoJSON must use WGS84 longitude/latitude (EPSG:4326)")
    if data.get("type") == "FeatureCollection":
        geometries = [shape(feature["geometry"]) for feature in data.get("features", []) if feature.get("geometry")]
    elif data.get("type") == "Feature":
        geometries = [shape(data["geometry"])]
    else:
        geometries = [shape(data)]
    if not geometries or any(g.geom_type not in ("Polygon", "MultiPolygon") or not g.is_valid or g.is_empty for g in geometries):
        raise ValueError("Boundary must contain valid Polygon/MultiPolygon geometry")
    aoi = unary_union(geometries)
    west, south, east, north = aoi.bounds
    if not (-180 <= west <= east <= 180 and -90 <= south <= north <= 90):
        raise ValueError("Boundary coordinates must be WGS84 longitude/latitude")
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    projected = _reproject(aoi, project)
    if not projected.is_valid:
        raise ValueError("Boundary is invalid after reprojection")
    clipped = _polygonal(footprint.intersection(projected))
    if clipped.is_empty or clipped.area <= 0:
        raise ValueError("Boundary does not overlap the orthomosaic")
    return clipped


def _cell_window(geometry: Any, dataset: Any) -> Window:
    floating = from_bounds(*geometry.bounds, transform=dataset.transform)
    left = max(0, math.floor(floating.col_off))
    top = max(0, math.floor(floating.row_off))
    right = min(dataset.width, math.ceil(floating.col_off + floating.width))
    bottom = min(dataset.height, math.ceil(floating.row_off + floating.height))
    return Window(left, top, max(0, right - left), max(0, bottom - top))


def _summarize(values: np.ndarray) -> dict[str, float | None]:
    names = ("mean", "median", "std", "min", "max", "p10", "p90")
    if not values.size:
        return {f"{name}_ndvi": None for name in names}
    return {
        "mean_ndvi": float(np.mean(values, dtype=np.float64)),
        "median_ndvi": float(np.median(values)),
        "std_ndvi": float(np.std(values, dtype=np.float64)),
        "min_ndvi": float(np.min(values)),
        "max_ndvi": float(np.max(values)),
        "p10_ndvi": float(np.percentile(values, 10)),
        "p90_ndvi": float(np.percentile(values, 90)),
    }


def _preview(ndvi_path: Path, vegetation_path: Path, target: Path) -> None:
    with rasterio.open(ndvi_path) as source, rasterio.open(vegetation_path) as mask:
        scale = min(1.0, 1200 / max(source.width, source.height))
        height, width = max(1, round(source.height * scale)), max(1, round(source.width * scale))
        values = source.read(1, out_shape=(height, width), resampling=Resampling.nearest)
        vegetation = mask.read(1, out_shape=(height, width), resampling=Resampling.nearest) == 1
    # A visual NDVI product only; this PNG never re-enters quantitative analysis.
    position = np.clip((values + 1) / 2, 0, 1)
    colors = np.empty((height, width, 4), dtype=np.uint8)
    stops = np.array([0, .5, .65, .8, 1])
    palette = np.array([[100, 60, 130], [180, 110, 40], [240, 210, 60], [120, 190, 60], [10, 95, 30]])
    for channel in range(3):
        colors[:, :, channel] = np.interp(position, stops, palette[:, channel]).astype(np.uint8)
    colors[:, :, 3] = np.where(vegetation, 255, 0).astype(np.uint8)
    Image.fromarray(colors).save(target)


def analyze_mosaic(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    config: dict,
    survey_id: str,
    plot_id: str,
    boundary_path: str | Path | None = None,
) -> dict[str, Any]:
    """Export NDVI, explicit masks and vegetation statistics per metric grid cell.

    All GeoTIFFs retain the input grid. Cell identifiers use floor(x/cell_size),
    floor(y/cell_size), anchored at projected CRS (0, 0), so overlapping surveys
    share cell IDs when their CRS and cell size match. Geometry exports use WGS84.
    Statistics describe vegetation pixels; bare soil/shadows never become alerts.
    """
    input_path, output_dir = Path(input_path), Path(output_dir)
    index_config = config.get("indices", config)
    grid_config = config.get("grid", {})
    red_band, nir_band = int(index_config.get("red_band", 1)), int(index_config.get("nir_band", 3))
    vegetation_threshold = float(index_config.get("vegetation_threshold", .2))
    brightness_min = float(index_config.get("brightness_min", .03))
    reflectance_scale = float(index_config.get("reflectance_scale", 1.0))
    cell_size = float(grid_config.get("cell_size_m", 5))
    max_cells = int(grid_config.get("max_cells", 100000))
    max_cell_pixels = int(grid_config.get("max_cell_pixels", 25_000_000))
    min_valid_fraction = float(grid_config.get("min_valid_fraction", .1))
    if not math.isfinite(cell_size) or cell_size <= 0 or not 1 <= max_cells < 2**32 or max_cell_pixels < 1:
        raise ValueError("Grid cell_size_m, max_cells and max_cell_pixels must be positive")
    if not 0 <= min_valid_fraction <= 1:
        raise ValueError("grid.min_valid_fraction must lie in [0, 1]")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: output_dir / filename for name, filename in {
        "ndvi": "ndvi.tif", "vegetation_mask": "vegetation_mask.tif", "shadow_mask": "shadow_mask.tif",
        "bare_soil_mask": "bare_soil_mask.tif", "grid_id": "grid_id.tif", "grid_geojson": "grid.geojson",
        "statistics_csv": "statistics.csv", "statistics_json": "statistics.json", "preview": "ndvi_preview.png",
    }.items()}
    if input_path.resolve() in [path.resolve() for path in paths.values()]:
        raise ValueError("Input mosaic cannot be overwritten by analysis output")
    with rasterio.open(input_path) as source:
        crs = _metric_crs(source)
        if red_band == nir_band or not (1 <= red_band <= source.count and 1 <= nir_band <= source.count):
            raise ValueError("Orthomosaic must contain distinct registered Red and NIR bands")
        area = _boundary(Path(boundary_path) if boundary_path else None, source.bounds, crs)
        min_col, min_row = math.floor(area.bounds[0] / cell_size), math.floor(area.bounds[1] / cell_size)
        max_col, max_row = math.ceil(area.bounds[2] / cell_size) - 1, math.ceil(area.bounds[3] / cell_size) - 1
        ncols, nrows = max_col - min_col + 1, max_row - min_row + 1
        if ncols * nrows > max_cells:
            raise ValueError(f"Grid would contain {ncols * nrows} cells, exceeding grid.max_cells={max_cells}; increase cell_size_m")
        largest_window = min(source.width, math.ceil(cell_size / source.transform.a) + 2) * min(
            source.height, math.ceil(cell_size / abs(source.transform.e)) + 2
        )
        if largest_window > max_cell_pixels:
            raise ValueError(f"Grid cells may exceed grid.max_cell_pixels={max_cell_pixels}; reduce cell_size_m")
        pixel_area = abs(source.transform.a * source.transform.e)
        counts = {"valid_pixel_count": 0, "vegetation_pixel_count": 0, "shadow_pixel_count": 0, "bare_soil_pixel_count": 0}
        with ExitStack() as stack:
            outputs = {
                "ndvi": stack.enter_context(rasterio.open(paths["ndvi"], "w", **output_profile(source, dtype="float32", nodata=NDVI_NODATA))),
                "grid_id": stack.enter_context(rasterio.open(paths["grid_id"], "w", **output_profile(source, dtype="uint32", nodata=0))),
            }
            for key in ("vegetation_mask", "shadow_mask", "bare_soil_mask"):
                outputs[key] = stack.enter_context(rasterio.open(paths[key], "w", **output_profile(source, dtype="uint8", nodata=MASK_NODATA)))
            for key, output in outputs.items():
                output.set_band_description(1, key)
                output.update_tags(survey_id=survey_id, plot_id=plot_id, source_mosaic=input_path.name,
                                   signal_units="relative; absolute accuracy not verified", vegetation_threshold=str(vegetation_threshold),
                                   brightness_min=str(brightness_min), reflectance_scale=str(reflectance_scale))
            outputs["grid_id"].update_tags(cell_size_m=str(cell_size), anchor_x="0", anchor_y="0", id_lookup="statistics.json")
            for window in _windows(source.width, source.height):
                red = source.read(red_band, window=window, masked=True)
                nir = source.read(nir_band, window=window, masked=True)
                inside = geometry_mask([mapping(area)], out_shape=red.shape, transform=window_transform(window, source.transform), invert=True)
                valid = inside & ~np.ma.getmaskarray(red) & ~np.ma.getmaskarray(nir)
                ndvi = calculate_ndvi(red, nir, valid_mask=valid)
                masks = build_masks(red, nir, ndvi, valid_mask=valid, vegetation_threshold=vegetation_threshold,
                                    brightness_min=brightness_min, reflectance_scale=reflectance_scale)
                outputs["ndvi"].write(ndvi, 1, window=window)
                for key, mask in (("vegetation_mask", "vegetation"), ("shadow_mask", "shadow"), ("bare_soil_mask", "bare_soil")):
                    outputs[key].write(as_mask_raster(masks[mask], masks["valid"]), 1, window=window)
                for count_name, mask_name in (("valid_pixel_count", "valid"), ("vegetation_pixel_count", "vegetation"),
                                              ("shadow_pixel_count", "shadow"), ("bare_soil_pixel_count", "bare_soil")):
                    counts[count_name] += int(np.count_nonzero(masks[mask_name]))
                cols = source.transform.c + (np.arange(int(window.col_off), int(window.col_off + window.width)) + .5) * source.transform.a
                rows = source.transform.f + (np.arange(int(window.row_off), int(window.row_off + window.height)) + .5) * source.transform.e
                world_cols = np.floor(cols / cell_size).astype(np.int64)
                world_rows = np.floor(rows / cell_size).astype(np.int64)
                ids = ((world_rows[:, None] - min_row) * ncols + (world_cols[None, :] - min_col) + 1)
                ids = np.where(inside, ids, 0).astype(np.uint32)
                outputs["grid_id"].write(ids, 1, window=window)
        unproject = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
        records = []
        with rasterio.open(paths["ndvi"]) as ndvi_source, rasterio.open(paths["grid_id"]) as grid_source, \
                rasterio.open(paths["vegetation_mask"]) as vegetation_source, rasterio.open(paths["shadow_mask"]) as shadow_source, \
                rasterio.open(paths["bare_soil_mask"]) as bare_source:
            for row in range(min_row, max_row + 1):
                for col in range(min_col, max_col + 1):
                    cell = _polygonal(box(col * cell_size, row * cell_size, (col + 1) * cell_size, (row + 1) * cell_size).intersection(area))
                    if cell.is_empty or cell.area <= 0:
                        continue
                    raster_id = (row - min_row) * ncols + col - min_col + 1
                    window = _cell_window(cell, source)
                    if window.width * window.height > max_cell_pixels:
                        raise ValueError(f"Cell {col},{row} exceeds grid.max_cell_pixels={max_cell_pixels}; reduce cell_size_m")
                    selected = grid_source.read(1, window=window) == raster_id
                    ndvi = ndvi_source.read(1, window=window)
                    vegetation = selected & (vegetation_source.read(1, window=window) == 1)
                    valid = selected & (ndvi != NDVI_NODATA) & np.isfinite(ndvi)
                    total_count, valid_count, vegetation_count = int(selected.sum()), int(valid.sum()), int(vegetation.sum())
                    coverage = valid_count / total_count if total_count else 0.0
                    qa_flags = []
                    if not valid_count:
                        qa_flags.append("no_valid_pixels")
                    if coverage < min_valid_fraction:
                        qa_flags.append("low_coverage")
                    if not vegetation_count:
                        qa_flags.append("no_vegetation")
                    record = {
                        "survey_id": str(survey_id), "plot_id": str(plot_id), "unit_id": f"{plot_id}:{col}:{row}",
                        "raster_id": int(raster_id), "row": int(row), "col": int(col), "cell_size_m": cell_size,
                        "area_m2": float(cell.area), "total_pixel_count": total_count, "valid_pixel_count": valid_count,
                        "vegetation_pixel_count": vegetation_count, "shadow_pixel_count": int(np.count_nonzero(selected & (shadow_source.read(1, window=window) == 1))),
                        "bare_soil_pixel_count": int(np.count_nonzero(selected & (bare_source.read(1, window=window) == 1))),
                        "vegetation_fraction": vegetation_count / valid_count if valid_count else 0.0,
                        "coverage_fraction": coverage, "vegetation_area_m2": vegetation_count * pixel_area,
                        "valid_area_m2": valid_count * pixel_area, "qa_usable": not qa_flags, "qa_flags": qa_flags,
                        **_summarize(ndvi[vegetation]), "geometry": mapping(cell),
                        "geometry_wgs84": mapping(_reproject(cell, unproject)),
                    }
                    records.append(record)
        crs_metadata = {"crs": crs.to_string(), "cell_size_m": cell_size, "anchor_x": 0.0, "anchor_y": 0.0,
                        "transform": list(source.transform)[:6], "width": source.width, "height": source.height,
                        "pixel_area_m2": pixel_area, "geometry_crs": crs.to_string(), "geojson_crs": "EPSG:4326"}
    feature_collection = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": row["unit_id"], "geometry": row["geometry_wgs84"],
         "properties": {k: v for k, v in row.items() if k not in ("geometry", "geometry_wgs84")}} for row in records
    ]}
    paths["grid_geojson"].write_text(json.dumps(feature_collection, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    paths["statistics_json"].write_text(json.dumps({"survey_id": survey_id, "plot_id": plot_id, "crs_metadata": crs_metadata,
                                                        "summary": counts, "records": records}, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    csv_fields = [k for k in records[0] if k not in ("geometry", "geometry_wgs84")] if records else ["survey_id", "plot_id", "unit_id", "mean_ndvi"]
    with paths["statistics_csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            writer.writerow({**row, "qa_flags": ";".join(row["qa_flags"])})
    _preview(paths["ndvi"], paths["vegetation_mask"], paths["preview"])
    return {"paths": {key: str(value) for key, value in paths.items()}, "records": records,
            "statistics": records, "cells": records, "crs": crs.to_string(), "crs_metadata": crs_metadata,
            "summary": counts}
