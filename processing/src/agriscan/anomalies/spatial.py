"""Method B: within-survey population z-score screening."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from typing import Any

from agriscan.anomalies.absolute import anomaly_config, config_mapping, eligible_units, method_enabled, setting


def spatial_threshold(config: Mapping[str, Any] | None = None) -> float:
    options = anomaly_config(config)
    legacy = config_mapping(options, "thresholds")
    nested = config_mapping(options, "spatial")
    value = options.get("spatial_z_threshold", nested.get("z_threshold", legacy.get("spatial_z_score")))
    threshold = setting({"spatial_z_threshold": -1.5 if value is None else value},
                        "spatial_z_threshold", -1.5)
    if threshold >= 0:
        raise ValueError("spatial_z_threshold must be negative for low-NDVI screening")
    return threshold


def spatial_analysis(
    records: Sequence[Mapping[str, Any]], config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Use the same eligible vegetation units for reference and detection."""
    options = anomaly_config(config)
    threshold = spatial_threshold(options)
    minimum = setting(options, "min_spatial_units", 3, minimum=3)
    if not minimum.is_integer():
        raise ValueError("min_spatial_units must be an integer")
    scale = setting(options, "spatial_strength_scale", 1.5, minimum=1e-12)
    units = eligible_units(records, options)
    values = [record["mean_ndvi"] for record in units]
    mean = statistics.fmean(values) if values else None
    sigma = statistics.pstdev(values) if values else None
    result: dict[str, Any] = {"candidates": [], "eligible_unit_count": len(units),
                             "mean_ndvi": mean, "population_stddev": sigma,
                             "z_threshold": threshold, "reference_scope": "current_plot_and_survey",
                             "status": "complete"}
    if not method_enabled(options, "spatial"):
        result["status"] = "disabled"
    elif len(units) < minimum:
        result["status"] = "insufficient_units"
    elif sigma is None or sigma <= 1e-12:
        result["status"] = "zero_variance"
    else:
        for record in units:
            z_score = (record["mean_ndvi"] - mean) / sigma
            if z_score < threshold:
                result["candidates"].append({**record, "anomaly_type": "spatial", "method": "B",
                    "index_name": "NDVI", "observed_value": record["mean_ndvi"],
                    "reference_value": mean, "z_score": z_score, "threshold": threshold,
                    "reference_stddev": sigma, "strength": min(1.0, (threshold - z_score) / scale),
                    "reason": f"Vegetation mean NDVI {record['mean_ndvi']:.4f} has population z-score {z_score:.4f}, below {threshold:.4f} in the current plot/survey; field inspection required."})
    return result


def detect_spatial(
    records: Sequence[Mapping[str, Any]], config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return spatial_analysis(records, config)["candidates"]
