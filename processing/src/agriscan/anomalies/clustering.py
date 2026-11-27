"""Merge edge-adjacent grid alerts while retaining their source unit IDs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from agriscan.anomalies.absolute import finite_number


def polygon_geometry(geometry: Any) -> dict[str, Any]:
    """Reject missing, empty, invalid, or non-polygon alert footprints."""
    if not isinstance(geometry, Mapping):
        raise ValueError("An alert requires a real Polygon/MultiPolygon geometry")
    try:
        polygon = shape(geometry)
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ValueError("Invalid alert geometry") from exc
    if polygon.is_empty or polygon.geom_type not in {"Polygon", "MultiPolygon"} or not polygon.is_valid:
        raise ValueError("Alert geometry must be a nonempty valid Polygon/MultiPolygon")
    if not all(finite_number(value) is not None for value in polygon.bounds):
        raise ValueError("Alert geometry contains nonfinite coordinates")
    return dict(mapping(polygon))


def _grid_location(record: Mapping[str, Any]) -> tuple[int, int] | None:
    row, col = finite_number(record.get("row")), finite_number(record.get("col"))
    if row is None or col is None or row != int(row) or col != int(col):
        return None
    return int(row), int(col)


def _aggregate(component: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(component, key=lambda item: item["unit_id"])
    representative = min(ordered, key=lambda item: (item["observed_value"], item["unit_id"]))
    merged = dict(representative)
    merged["unit_ids"] = [item["unit_id"] for item in ordered]
    merged["unit_count"] = len(ordered)
    merged["geometry"] = polygon_geometry(mapping(unary_union([shape(item["geometry"]) for item in ordered])))
    weights = [max(1, item.get("vegetation_pixel_count", 1)) for item in ordered]
    weight_sum = sum(weights)
    merged["observed_value"] = sum(item["observed_value"] * weight for item, weight in zip(ordered, weights)) / weight_sum
    merged["mean_ndvi"] = merged["observed_value"]
    merged["reference_value"] = sum(item["reference_value"] * weight for item, weight in zip(ordered, weights)) / weight_sum
    merged["strength"] = max(item["strength"] for item in ordered)
    merged["minimum_unit_ndvi"] = min(item["observed_value"] for item in ordered)
    if finite_number(merged.get("reference_stddev")) is not None and merged["reference_stddev"] > 0:
        merged["most_extreme_unit_z_score"] = min(item["z_score"] for item in ordered)
        merged["z_score"] = (merged["observed_value"] - merged["reference_value"]) / merged["reference_stddev"]
    merged["valid_pixel_count"] = sum(item.get("valid_pixel_count", 0) for item in ordered)
    merged["vegetation_pixel_count"] = sum(item.get("vegetation_pixel_count", 0) for item in ordered)
    merged["vegetation_fraction"] = merged["vegetation_pixel_count"] / merged["valid_pixel_count"] if merged["valid_pixel_count"] else 0.0
    for key in ("total_pixel_count", "shadow_pixel_count", "bare_soil_pixel_count", "vegetation_area_m2", "valid_area_m2"):
        values = [finite_number(item.get(key)) for item in ordered]
        if all(value is not None and value >= 0 for value in values):
            merged[key] = sum(values)
    if merged.get("total_pixel_count", 0) > 0:
        merged["coverage_fraction"] = merged["valid_pixel_count"] / merged["total_pixel_count"]
    areas = [finite_number(item.get("area_m2")) for item in ordered]
    merged["area_m2"] = sum(areas) if all(area is not None and area >= 0 for area in areas) else None
    merged["agreement_fraction"] = sum(item.get("method_agreement", False) * weight for item, weight in zip(ordered, weights)) / weight_sum
    if len(ordered) > 1:
        merged["reason"] += f" Merged {len(ordered)} edge-adjacent units; representative unit {representative['unit_id']}; severity uses the largest deviation."
    return merged


def merge_adjacent_candidates(
    candidates: Sequence[Mapping[str, Any]], *, enabled: bool = True,
) -> list[dict[str, Any]]:
    """Merge only the same method; diagonal contacts are separate alerts.

    Geometry is expected to be in one common CRS. Four-neighbor grid locations
    establish adjacency; actual shared polygon edges must also be present.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        record = dict(item)
        record["geometry"] = polygon_geometry(record.get("geometry"))
        groups[str(record["anomaly_type"])].append(record)
    result = []
    for anomaly_type in sorted(groups):
        items = sorted(groups[anomaly_type], key=lambda item: item["unit_id"])
        if not enabled:
            result.extend(_aggregate([item]) for item in items)
            continue
        locations = [_grid_location(item) for item in items]
        lookup: dict[tuple[int, int], list[int]] = defaultdict(list)
        for index, location in enumerate(locations):
            if location is not None:
                lookup[location].append(index)
        polygons = [shape(item["geometry"]) for item in items]
        visited: set[int] = set()
        for start in range(len(items)):
            if start in visited:
                continue
            visited.add(start)
            component, pending = [], [start]
            while pending:
                current = pending.pop()
                component.append(items[current])
                location = locations[current]
                if location is not None:
                    row, col = location
                    neighbors = [index for key in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)) for index in lookup.get(key, [])]
                    neighbors.extend(index for index, candidate_location in enumerate(locations) if candidate_location is None)
                else:
                    neighbors = range(len(items))
                for index in neighbors:
                    if index in visited:
                        continue
                    first, second = polygons[current], polygons[index]
                    if first.touches(second) and first.boundary.intersection(second.boundary).length > 0:
                        visited.add(index)
                        pending.append(index)
            result.append(_aggregate(component))
    return result
