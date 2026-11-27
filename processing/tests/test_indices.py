"""Numerical and geospatial contracts for registered spectral mosaics."""

from __future__ import annotations

import json

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely import transform as coordinate_transform
from shapely.geometry import MultiPolygon, box, mapping, shape

from agriscan.indices.masking import MASK_NODATA, as_mask_raster, build_masks
from agriscan.indices.ndvi import NDVI_NODATA, calculate_ndvi
from agriscan.indices.statistics import analyze_mosaic
from agriscan.indices import statistics
from agriscan.io.raster_io import assert_same_grid, read_registered_bands, write_geotiff


def _mosaic(tmp_path, *, transform=None, crs="EPSG:32648", shape=(8, 10), red=.1, nir=.6, name="mosaic.tif"):
    values = np.empty((3, *shape), dtype=np.float32)
    values[0], values[1], values[2] = red, .2, nir
    transform = transform or from_origin(500001, 1200017, 1, 1)
    path = tmp_path / name
    write_geotiff(path, values, {"driver": "GTiff", "crs": crs, "transform": transform}, nodata=-9999)
    return path


def _analyze(path, target, **kwargs):
    config = {"indices": {"red_band": 1, "nir_band": 3, "vegetation_threshold": .2, "brightness_min": .03},
              "grid": {"cell_size_m": 5}}
    config.update(kwargs.pop("config", {}))
    return analyze_mosaic(path, target, config=config, survey_id="survey-a", plot_id="plot-a", **kwargs)


def test_ndvi_formula_and_invalid_values():
    red = np.array([.2, .1, 0, -.1, np.nan, .2, .2])
    nir = np.array([.6, .1, 0, .5, .4, np.inf, -.1])
    result = calculate_ndvi(red, nir)
    np.testing.assert_allclose(result[:2], [.5, 0], atol=1e-6)
    np.testing.assert_array_equal(result[2:], NDVI_NODATA)
    assert result.dtype == np.float32


def test_masked_source_and_registration_shape():
    red = np.ma.array([.1, .1], mask=[True, False])
    result = calculate_ndvi(red, np.array([.4, .4]))
    assert result[0] == NDVI_NODATA
    assert result[1] == pytest.approx(.6)
    with pytest.raises(ValueError, match="same shape"):
        calculate_ndvi(np.ones((2, 2)), np.ones((3, 2)))


def test_masks_retain_stressed_vegetation_and_exclude_dark_soil():
    red = np.array([.1, .3, .001, 0])
    nir = np.array([.18, .31, .008, 0])
    ndvi = calculate_ndvi(red, nir)
    masks = build_masks(red, nir, ndvi, vegetation_threshold=.2, brightness_min=.03)
    np.testing.assert_array_equal(masks["vegetation"], [True, False, False, False])
    np.testing.assert_array_equal(masks["bare_soil"], [False, True, False, False])
    np.testing.assert_array_equal(masks["shadow"], [False, False, True, False])
    np.testing.assert_array_equal(as_mask_raster(masks["vegetation"], masks["valid"]), [1, 0, 0, MASK_NODATA])


def test_shadow_threshold_uses_fixed_signal_scale():
    red, nir = np.array([.001, .1]), np.array([.008, .6])
    floats = build_masks(red, nir, calculate_ndvi(red, nir))
    integers = build_masks(red * 16384, nir * 16384, calculate_ndvi(red, nir), reflectance_scale=16384)
    np.testing.assert_array_equal(floats["shadow"], integers["shadow"])


def test_raster_registration_rejects_crs_and_transform_mismatch(tmp_path):
    first = _mosaic(tmp_path)
    shifted = _mosaic(tmp_path, transform=from_origin(500002, 1200017, 1, 1), name="shift.tif")
    other_crs = _mosaic(tmp_path, crs="EPSG:32647", name="crs.tif")
    assert_same_grid(first, first)
    for path in (shifted, other_crs):
        with pytest.raises(ValueError, match="same CRS"):
            read_registered_bands(first, path, red_band=1, nir_band=3)


def test_analysis_preserves_geometry_counts_statistics_and_exports(tmp_path):
    path = _mosaic(tmp_path)
    result = _analyze(path, tmp_path / "result")
    assert result["summary"]["valid_pixel_count"] == 80
    assert result["summary"]["vegetation_pixel_count"] == 80
    assert sum(cell["valid_pixel_count"] for cell in result["records"]) == 80
    assert sum(cell["area_m2"] for cell in result["records"]) == pytest.approx(80)
    for cell in result["records"]:
        assert cell["mean_ndvi"] == pytest.approx(5 / 7)
        assert cell["coverage_fraction"] == 1
        assert cell["vegetation_fraction"] == 1
        assert shape(cell["geometry"]).area == pytest.approx(cell["area_m2"])
        assert cell["unit_id"] == f"plot-a:{cell['col']}:{cell['row']}"
        assert cell["qa_usable"]
    with rasterio.open(path) as original, rasterio.open(result["paths"]["ndvi"]) as ndvi:
        assert ndvi.transform == original.transform
        assert ndvi.crs == original.crs
        assert ndvi.nodata == NDVI_NODATA
        assert ndvi.dtypes == ("float32",)
    with rasterio.open(result["paths"]["vegetation_mask"]) as mask:
        assert mask.dtypes == ("uint8",)
        assert mask.nodata == MASK_NODATA
    geojson = json.loads((tmp_path / "result/grid.geojson").read_text())
    for feature in geojson["features"]:
        west, south, east, north = shape(feature["geometry"]).bounds
        assert -180 <= west <= east <= 180
        assert -90 <= south <= north <= 90
    assert (tmp_path / "result/statistics.csv").exists()
    assert (tmp_path / "result/ndvi_preview.png").exists()


def test_grid_world_anchor_matches_across_shifted_footprints(tmp_path):
    first = _mosaic(tmp_path, shape=(10, 10), transform=from_origin(500000, 1200020, 1, 1))
    shifted = _mosaic(tmp_path, shape=(10, 10), transform=from_origin(500003, 1200023, 1, 1), name="shift.tif")
    a = _analyze(first, tmp_path / "a")
    b = _analyze(shifted, tmp_path / "b")
    cells_a = {cell["unit_id"]: cell for cell in a["records"]}
    cells_b = {cell["unit_id"]: cell for cell in b["records"]}
    common = cells_a.keys() & cells_b.keys()
    assert common
    for name in common:
        # Clipped outer footprints can differ, but both occupy the same world cell.
        left = cells_a[name]["col"] * 5
        south = cells_a[name]["row"] * 5
        full_cell = box(left, south, left + 5, south + 5)
        assert full_cell.covers(shape(cells_a[name]["geometry"]))
        assert full_cell.covers(shape(cells_b[name]["geometry"]))


def test_aoi_clips_geometry_and_statistics(tmp_path):
    transform = from_origin(500000, 1200020, 1, 1)
    path = _mosaic(tmp_path, shape=(10, 10), transform=transform)
    unproject = Transformer.from_crs("EPSG:32648", "EPSG:4326", always_xy=True).transform
    polygon = coordinate_transform(box(500002, 1200012, 500008, 1200018), lambda xy: np.column_stack(unproject(xy[:, 0], xy[:, 1])))
    boundary = tmp_path / "boundary.geojson"
    boundary.write_text(json.dumps({"type": "Feature", "geometry": mapping(polygon), "properties": {}}))
    result = _analyze(path, tmp_path / "result", boundary_path=boundary)
    assert result["summary"]["valid_pixel_count"] == 36
    assert sum(cell["area_m2"] for cell in result["records"]) == pytest.approx(36, abs=.0001)
    assert sum(cell["valid_pixel_count"] for cell in result["records"]) == 36


def test_coverage_excludes_nodata_from_vegetation_statistics(tmp_path):
    red = np.full((5, 5), .1, np.float32)
    nir = np.full((5, 5), .6, np.float32)
    red[0, :] = -9999
    nir[1, :] = .001
    red[1, :] = .001
    path = _mosaic(tmp_path, shape=(5, 5), transform=from_origin(500000, 1200020, 1, 1), red=red, nir=nir)
    result = _analyze(path, tmp_path / "result")
    cell = result["records"][0]
    assert cell["total_pixel_count"] == 25
    assert cell["valid_pixel_count"] == 20
    assert cell["vegetation_pixel_count"] == 15
    assert cell["shadow_pixel_count"] == 5
    assert cell["coverage_fraction"] == pytest.approx(.8)
    assert cell["mean_ndvi"] == pytest.approx(5 / 7)


def test_geographic_input_never_gets_fake_metric_grid(tmp_path):
    path = _mosaic(tmp_path, crs="EPSG:4326", transform=from_origin(105, 11, .0001, .0001))
    with pytest.raises(ValueError, match="projected CRS in metres"):
        _analyze(path, tmp_path / "result")


def test_grid_and_cell_memory_limits_are_actionable(tmp_path):
    path = _mosaic(tmp_path)
    with pytest.raises(ValueError, match="max_cells"):
        _analyze(path, tmp_path / "a", config={"grid": {"cell_size_m": .01, "max_cells": 10}})
    with pytest.raises(ValueError, match="max_cell_pixels"):
        _analyze(path, tmp_path / "b", config={"grid": {"cell_size_m": 5, "max_cell_pixels": 1}})


def test_all_invalid_cell_has_null_statistics_and_no_nan_json(tmp_path):
    path = _mosaic(tmp_path, red=0, nir=0)
    result = _analyze(path, tmp_path / "result")
    for cell in result["records"]:
        assert cell["mean_ndvi"] is None
        assert not cell["qa_usable"]
        assert "no_valid_pixels" in cell["qa_flags"]
    payload = (tmp_path / "result/statistics.json").read_text()
    assert "NaN" not in payload


def test_multipart_aoi_touching_raster_edge_discards_line_fragments(tmp_path, monkeypatch):
    """A disjoint AOI part outside the image must not add boundary-only pixels."""
    path = _mosaic(tmp_path, shape=(10, 10), transform=from_origin(500000, 1200020, 1, 1))
    projected_aoi = MultiPolygon([box(500001, 1200011, 500004, 1200014),
                                  box(500010, 1200011, 500014, 1200014)])
    boundary = tmp_path / 'boundary.geojson'
    boundary.write_text(json.dumps(mapping(box(105, 10, 105.001, 10.001))))
    # Isolate exact projected edge contact from round-trip projection rounding.
    monkeypatch.setattr(statistics, '_reproject', lambda *_: projected_aoi)
    with rasterio.open(path) as source:
        clipped = statistics._boundary(boundary, source.bounds, statistics._metric_crs(source))
        assert clipped.geom_type == 'Polygon'
        assert clipped.area == 9
        from rasterio.features import geometry_mask
        selected = geometry_mask([mapping(clipped)], (source.height, source.width), source.transform, invert=True)
        assert int(selected.sum()) == 9
        assert not selected[:, -1].any()


def test_multipart_grid_clipping_exports_only_polygons_accepted_by_alerts(tmp_path, monkeypatch):
    """A neighboring AOI island that only touches a cell cannot break alerts."""
    from agriscan.anomalies.ranking import generate_alerts
    path = _mosaic(tmp_path, shape=(10, 10), transform=from_origin(500000, 1200020, 1, 1), red=.24, nir=.4)
    projected_aoi = MultiPolygon([box(500001, 1200010, 500004, 1200015),
                                  box(500005, 1200010, 500009, 1200015)])
    monkeypatch.setattr(statistics, '_boundary', lambda *_: projected_aoi)
    result = _analyze(path, tmp_path / 'result')
    assert result['summary']['valid_pixel_count'] == 35
    assert sum(cell['area_m2'] for cell in result['records']) == 35
    assert all(cell['geometry']['type'] in ('Polygon', 'MultiPolygon') for cell in result['records'])
    assert all(cell['geometry_wgs84']['type'] in ('Polygon', 'MultiPolygon') for cell in result['records'])
    alerts = generate_alerts(result['records'], survey_id='survey-a', plot_id='plot-a',
                             config={'anomaly': {'min_valid_pixels': 1}}, output_dir=tmp_path / 'alerts', crs=result['crs'])
    assert alerts['method_a_count'] == 2
