"""Deterministic alert ranking and WGS84 Group C handoff artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from rasterio.warp import transform_geom
from shapely.geometry import shape

from agriscan.anomalies.absolute import (
    absolute_threshold, anomaly_config, detect_absolute, eligible_units, finite_number, setting,
)
from agriscan.anomalies.clustering import merge_adjacent_candidates, polygon_geometry
from agriscan.anomalies.spatial import spatial_analysis


def rank_alerts(
    candidates: Sequence[Mapping[str, Any]], *, config: Mapping[str, Any] | None = None,
    survey_id: str, plot_id: str, total_area_m2: float | None = None,
) -> list[dict[str, Any]]:
    """Score 0–100 from configured deviation, affected area, and A/B agreement."""
    options = anomaly_config(config)
    ranking = options.get("ranking", {}) or {}
    if not isinstance(ranking, Mapping):
        raise ValueError("anomaly.ranking must be a mapping")
    weights = ranking.get("weights", ranking)
    if not isinstance(weights, Mapping):
        raise ValueError("anomaly.ranking.weights must be a mapping")
    severity_weight = setting(weights, "severity", weights.get("severity_weight", 0.7), minimum=0)
    area_weight = setting(weights, "area", weights.get("area_weight", 0.2), minimum=0)
    agreement_weight = setting(weights, "agreement", weights.get("agreement_weight", 0.1), minimum=0)
    weight_sum = severity_weight + area_weight + agreement_weight
    if weight_sum <= 0:
        raise ValueError("At least one anomaly ranking weight must be positive")
    medium = setting(ranking, "medium_strength", 1 / 3, minimum=0, maximum=1)
    high = setting(ranking, "high_strength", 2 / 3, minimum=0, maximum=1)
    if medium >= high:
        raise ValueError("medium_strength must be smaller than high_strength")
    result = []
    for candidate in candidates:
        item = dict(candidate)
        strength = finite_number(item.get("strength"))
        if strength is None or not 0 <= strength <= 1:
            raise ValueError("Candidate strength must be finite and within [0, 1]")
        area = finite_number(item.get("area_m2"))
        area_fraction = min(1.0, max(0.0, area / total_area_m2)) if area is not None and total_area_m2 is not None and total_area_m2 > 0 else 0.0
        agreement = finite_number(item.get("agreement_fraction", item.get("method_agreement", 0)))
        # bool is intentionally accepted for a single-unit method agreement.
        if agreement is None:
            agreement = float(bool(item.get("method_agreement", False)))
        agreement = min(1.0, max(0.0, agreement))
        score = 100 * (severity_weight * strength + area_weight * area_fraction + agreement_weight * agreement) / weight_sum
        units = sorted(item.get("unit_ids", [item["unit_id"]]))
        identity = json.dumps([str(survey_id), str(plot_id), item["anomaly_type"], units], separators=(",", ":"), ensure_ascii=True)
        item.update(alert_code="ALT-" + hashlib.sha256(identity.encode()).hexdigest()[:16].upper(),
                    survey_id=str(survey_id), plot_id=str(plot_id), unit_ids=units,
                    index_name="NDVI", severity="high" if strength >= high else "medium" if strength >= medium else "low",
                    priority_score=round(min(100.0, max(0.0, score)), 6), area_fraction=area_fraction,
                    agreement_fraction=agreement, status="PENDING", evidence_type="screening",
                    threshold_status="experimental")
        result.append(item)
    result.sort(key=lambda item: (-item["priority_score"], item["anomaly_type"], tuple(item["unit_ids"])))
    for rank, item in enumerate(result, 1):
        item["priority_rank"] = rank
    return result


def _wgs84_geometry(record: Mapping[str, Any], crs: Any) -> dict[str, Any]:
    geometry = record.get("geometry_wgs84")
    if geometry is None:
        geometry = polygon_geometry(record.get("geometry"))
        if crs is None:
            raise ValueError("A source CRS or geometry_wgs84 is required for alert export")
        geometry = transform_geom(crs, "EPSG:4326", geometry, precision=12)
    geometry = polygon_geometry(geometry)
    xmin, ymin, xmax, ymax = shape(geometry).bounds
    if not (-180 <= xmin <= xmax <= 180 and -90 <= ymin <= ymax <= 90):
        raise ValueError("WGS84 alert coordinates are outside longitude/latitude bounds")
    return geometry


def generate_alerts(
    records: Sequence[Mapping[str, Any]], *, survey_id: str, plot_id: str,
    config: Mapping[str, Any] | None, output_dir: str | Path, crs: Any,
) -> dict[str, Any]:
    """Create one reproducible alert set for one plot in one survey.

    Both methods screen vegetation NDVI within this input only. No temporal
    comparison, absolute reflectance accuracy, or disease diagnosis is implied.
    """
    if not str(survey_id).strip() or not str(plot_id).strip():
        raise ValueError("survey_id and plot_id are required")
    options = anomaly_config(config)
    for record in records:
        for key, expected in (("survey_id", str(survey_id)), ("plot_id", str(plot_id))):
            if record.get(key) is not None and str(record[key]) != expected:
                raise ValueError(f"Cannot mix different {key} values in one anomaly analysis")
    eligible = eligible_units(records, options)
    absolute = detect_absolute(eligible, options)
    spatial = spatial_analysis(eligible, options)
    candidates = absolute + spatial["candidates"]
    detected: dict[str, set[str]] = defaultdict(set)
    for item in candidates:
        detected[item["unit_id"]].add(item["method"])
    for item in candidates:
        item["method_agreement"] = len(detected[item["unit_id"]]) == 2
        item["geometry"] = _wgs84_geometry(item, crs)
        item.pop("geometry_wgs84", None)
    merge = options.get("merge_adjacent", True)
    if not isinstance(merge, bool):
        raise ValueError("anomaly.merge_adjacent must be true or false")
    merged = merge_adjacent_candidates(candidates, enabled=merge)
    areas = [finite_number(record.get("area_m2")) for record in eligible]
    total_area = sum(areas) if areas and all(area is not None and area >= 0 for area in areas) else None
    alerts = rank_alerts(merged, config=options, survey_id=survey_id, plot_id=plot_id, total_area_m2=total_area)
    features = []
    for alert in alerts:
        properties = {key: value for key, value in alert.items() if key not in {"geometry", "row", "col"}}
        features.append({"type": "Feature", "geometry": alert["geometry"], "properties": properties})
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    geojson_path, csv_path = destination / "alerts.geojson", destination / "alerts.csv"
    collection = {"type": "FeatureCollection", "features": features,
                  "metadata": {"survey_id": str(survey_id), "plot_id": str(plot_id),
                               "coordinate_reference_system": "EPSG:4326", "evidence_type": "screening",
                               "threshold_status": "experimental"}}
    geojson_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    columns = ["alert_code", "survey_id", "plot_id", "unit_id", "unit_ids", "index_name", "method",
               "observed_value", "reference_value", "anomaly_type", "severity", "priority_score",
               "priority_rank", "area_m2", "area_fraction", "agreement_fraction", "threshold",
               "z_score", "reason", "threshold_status", "geometry"]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for alert in alerts:
            row = dict(alert)
            row["unit_ids"] = json.dumps(row["unit_ids"], ensure_ascii=False)
            row["geometry"] = json.dumps(row["geometry"], separators=(",", ":"), allow_nan=False)
            writer.writerow(row)
    spatial_report = {key: value for key, value in spatial.items() if key != "candidates"}
    report = {"survey_id": str(survey_id), "plot_id": str(plot_id), "input_unit_count": len(records),
              "eligible_unit_count": len(eligible), "excluded_unit_count": len(records) - len(eligible),
              "candidate_count": len(candidates), "alert_count": len(alerts),
              "method_a_count": len(absolute), "method_b_count": len(spatial["candidates"]),
              "counts_by_type": dict(Counter(item["anomaly_type"] for item in alerts)),
              "counts_by_severity": dict(Counter(item["severity"] for item in alerts)),
              "absolute_threshold": absolute_threshold(options), "spatial": spatial_report,
              "threshold_status": "experimental", "coordinate_reference_system": "EPSG:4326",
              "ranking_reference_area_m2": total_area,
              "ranking_area_scope": "sum_of_eligible_unit_footprints",
              "ranking": options.get("ranking", {"weights": {"severity": 0.7, "area": 0.2, "agreement": 0.1}}),
              "paths": {"alerts_geojson": str(geojson_path), "alerts_csv": str(csv_path)}, "alerts": alerts}
    report_path = destination / "anomaly_report.json"
    report_path.write_text(json.dumps({key: value for key, value in report.items() if key != "alerts"}, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report["paths"]["anomaly_report"] = str(report_path)
    return report
