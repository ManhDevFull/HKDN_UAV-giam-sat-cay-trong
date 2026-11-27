"""Scientific edge cases and the Group C alert contract."""

from __future__ import annotations

import json
import math

import pytest
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping, shape

from agriscan.anomalies.absolute import detect_absolute, eligible_units
from agriscan.anomalies.clustering import merge_adjacent_candidates
from agriscan.anomalies.ranking import generate_alerts, rank_alerts
from agriscan.anomalies.spatial import detect_spatial, spatial_analysis


def unit(number, ndvi, *, row=0, col=None, **changes):
    col = number if col is None else col
    record = {"unit_id": f"unit-{number:03}", "mean_ndvi": ndvi,
              "valid_pixel_count": 100, "vegetation_pixel_count": 80,
              "vegetation_fraction": 0.8, "coverage_fraction": 1,
              "area_m2": 100, "row": row, "col": col,
              "geometry": mapping(box(500000 + col * 10, 1200000 + row * 10,
                                       500010 + col * 10, 1200010 + row * 10))}
    record.update(changes)
    return record


def candidate(number, ndvi=0.3, **changes):
    record = detect_absolute([unit(number, ndvi)])[0]
    record.update(changes)
    return record


def test_method_a_strict_boundary_and_no_input_mutation():
    records = [unit(0, 0.35), unit(1, 0.349), unit(2, 0.7)]
    result = detect_absolute(records)
    assert [item["unit_id"] for item in result] == ["unit-001"]
    assert result[0]["method"] == "A"
    assert result[0]["reference_value"] == 0.35
    assert "method" not in records[1]


@pytest.mark.parametrize("changes", [
    {"mean_ndvi": None}, {"mean_ndvi": math.nan}, {"mean_ndvi": math.inf},
    {"mean_ndvi": -2}, {"valid_pixel_count": 9}, {"vegetation_pixel_count": 0},
    {"vegetation_fraction": 0.05}, {"coverage_fraction": 0.1}, {"usable": False}, {"qa_usable": False},
])
def test_low_quality_and_masked_units_do_not_create_alerts(changes):
    assert not detect_absolute([unit(1, 0.25, **changes)])


def test_method_b_population_z_score_and_invalid_reference_exclusion():
    records = [unit(index, value) for index, value in enumerate([0.25, 0.7, 0.7, 0.7, 0.7, 0.7])]
    records += [unit(99, -0.8, vegetation_pixel_count=0)]
    result = spatial_analysis(records)
    assert result["eligible_unit_count"] == 6
    assert len(result["candidates"]) == 1
    alert = result["candidates"][0]
    assert alert["unit_id"] == "unit-000"
    assert alert["z_score"] == pytest.approx(-math.sqrt(5))
    assert alert["reference_value"] == pytest.approx(0.625)
    assert alert["method"] == "B"


def test_method_b_handles_empty_insufficient_and_zero_variance():
    assert spatial_analysis([])["status"] == "insufficient_units"
    assert spatial_analysis([unit(1, 0.3), unit(2, 0.7)])["status"] == "insufficient_units"
    result = spatial_analysis([unit(index, 0.7) for index in range(5)])
    assert result["status"] == "zero_variance"
    assert result["candidates"] == []


def test_method_b_strict_threshold_boundary():
    records = [unit(index, value) for index, value in enumerate([0.25, 0.7, 0.7, 0.7])]
    first = detect_spatial(records, {"spatial_z_threshold": -1})[0]
    assert detect_spatial(records, {"spatial_z_threshold": first["z_score"]}) == []


def test_config_and_duplicate_unit_validation():
    with pytest.raises(ValueError, match="Duplicate"):
        eligible_units([unit(1, 0.3), unit(1, 0.5)])
    with pytest.raises(ValueError, match="negative"):
        detect_spatial([], {"spatial_z_threshold": 0})
    with pytest.raises(ValueError, match="min_vegetation_fraction"):
        eligible_units([], {"min_vegetation_fraction": 2})
    with pytest.raises(ValueError, match="integer"):
        eligible_units([], {"min_valid_pixels": 1.5})
    with pytest.raises(ValueError, match="mapping"):
        detect_absolute([], {"methods": "absolute"})
    with pytest.raises(ValueError, match="true or false"):
        detect_spatial([], {"methods": {"spatial": "false"}})
    assert detect_absolute([unit(1, 0.3)], {"anomaly": {"methods": {"absolute": False}}}) == []


def test_stronger_signal_ranks_higher_and_scores_stay_bounded():
    candidates = [candidate(1, 0.34), candidate(2, 0.21)]
    ranked = rank_alerts(candidates, config={}, survey_id="S1", plot_id="P1", total_area_m2=200)
    assert ranked[0]["unit_id"] == "unit-002"
    assert ranked[0]["priority_score"] > ranked[1]["priority_score"]
    assert ranked[0]["severity"] == "high"
    assert ranked[1]["severity"] == "low"
    assert all(0 <= item["priority_score"] <= 100 for item in ranked)


def test_method_agreement_and_explicit_ranking_weights():
    candidates = [candidate(1, method_agreement=False), candidate(2, method_agreement=True)]
    ranked = rank_alerts(candidates, config={"ranking": {"weights": {"severity": 0, "area": 0, "agreement": 1}}}, survey_id="S", plot_id="P")
    assert [item["priority_score"] for item in ranked] == [100, 0]
    assert ranked[0]["unit_id"] == "unit-002"
    with pytest.raises(ValueError, match="positive"):
        rank_alerts([], config={"ranking": {"weights": {"severity": 0, "area": 0, "agreement": 0}}}, survey_id="S", plot_id="P")


def test_clustering_merges_edges_preserves_diagonals_and_method_types():
    first = candidate(1)
    second = candidate(2)
    diagonal = candidate(3, row=1, col=3, geometry=unit(3, 0.3, row=1, col=3)["geometry"])
    other_method = {**first, "method": "B", "anomaly_type": "spatial"}
    merged = merge_adjacent_candidates([diagonal, second, other_method, first])
    assert len(merged) == 3
    absolute = [item for item in merged if item["anomaly_type"] == "absolute"]
    assert [item["unit_count"] for item in absolute] == [2, 1]
    assert absolute[0]["unit_ids"] == ["unit-001", "unit-002"]
    assert shape(absolute[0]["geometry"]).area == pytest.approx(200)
    assert absolute[0]["area_m2"] == pytest.approx(200)
    assert len(merge_adjacent_candidates([first, second], enabled=False)) == 2


def test_export_reprojects_and_codes_are_stable(tmp_path):
    records = [unit(index, value) for index, value in enumerate([0.25, 0.7, 0.7, 0.7, 0.7, 0.7])]
    result = generate_alerts(records, survey_id="S1", plot_id="P1", config={}, output_dir=tmp_path, crs="EPSG:32648")
    assert result["method_a_count"] == result["method_b_count"] == 1
    assert result["alert_count"] == 2
    data = json.loads((tmp_path / "alerts.geojson").read_text())
    expected = shape(transform_geom("EPSG:32648", "EPSG:4326", records[0]["geometry"]))
    for feature in data["features"]:
        geometry = shape(feature["geometry"])
        assert geometry.is_valid and not geometry.is_empty
        assert geometry.hausdorff_distance(expected) < 1e-9
        assert 100 < geometry.bounds[0] < 110
        assert feature["properties"]["threshold_status"] == "experimental"
        assert feature["properties"]["survey_id"] == "S1"
        assert feature["properties"]["agreement_fraction"] == 1
    rerun = generate_alerts(list(reversed(records)), survey_id="S1", plot_id="P1", config={}, output_dir=tmp_path, crs="EPSG:32648")
    assert [item["alert_code"] for item in result["alerts"]] == [item["alert_code"] for item in rerun["alerts"]]
    assert data == json.loads((tmp_path / "alerts.geojson").read_text())
    assert (tmp_path / "alerts.csv").read_text().count("ALT-") == 2


def test_export_empty_alerts_and_rejects_mixed_surveys(tmp_path):
    result = generate_alerts([], survey_id="S", plot_id="P", config={}, output_dir=tmp_path, crs="EPSG:32648")
    assert result["alert_count"] == 0
    assert json.loads((tmp_path / "alerts.geojson").read_text())["features"] == []
    with pytest.raises(ValueError, match="survey_id"):
        generate_alerts([unit(1, 0.3, survey_id="OTHER")], survey_id="S", plot_id="P", config={}, output_dir=tmp_path, crs="EPSG:32648")


@pytest.mark.parametrize("geometry", [None, {"type": "Polygon", "coordinates": []}, mapping(box(1, 1, 1, 2))])
def test_export_rejects_empty_or_invalid_geometry(geometry, tmp_path):
    with pytest.raises(ValueError, match="geometry|Polygon"):
        generate_alerts([unit(1, 0.3, geometry=geometry)], survey_id="S", plot_id="P", config={}, output_dir=tmp_path, crs="EPSG:32648")
