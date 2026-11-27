"""Method A: configurable NDVI screening on vegetation statistics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


def anomaly_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Accept a whole pipeline configuration or its ``anomaly`` section."""
    config = config or {}
    if not isinstance(config, Mapping):
        raise ValueError("anomaly configuration must be a mapping")
    section = config.get("anomaly", config.get("anomalies", config))
    if not isinstance(section, Mapping):
        raise ValueError("anomaly must be a configuration mapping")
    return dict(section)


def config_mapping(config: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = config.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"anomaly.{key} must be a mapping")
    return value


def method_enabled(config: Mapping[str, Any], method: str) -> bool:
    methods = config_mapping(config, "methods")
    nested = config_mapping(config, method)
    switches = (methods.get(method, True), nested.get("enabled", True))
    if any(not isinstance(value, bool) for value in switches):
        raise ValueError(f"anomaly method {method}.enabled must be true or false")
    return all(switches)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def setting(
    config: Mapping[str, Any], key: str, default: float,
    *, minimum: float | None = None, maximum: float | None = None,
) -> float:
    value = finite_number(config.get(key, default))
    if value is None or (minimum is not None and value < minimum) or (
        maximum is not None and value > maximum
    ):
        raise ValueError(f"Invalid anomaly setting {key}: {config.get(key)!r}")
    return value


def eligible_units(
    records: Sequence[Mapping[str, Any]], config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Drop masked, missing, or insufficiently sampled grid cells."""
    options = anomaly_config(config)
    minimum_pixels = setting(options, "min_valid_pixels", 10, minimum=1)
    if not minimum_pixels.is_integer():
        raise ValueError("min_valid_pixels must be an integer")
    minimum_vegetation = setting(options, "min_vegetation_fraction", 0.1, minimum=0, maximum=1)
    minimum_coverage = setting(options, "min_coverage_fraction", 0.2, minimum=0, maximum=1)
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in records:
        record = dict(source)
        unit_id = str(record.get("unit_id", record.get("cell_id", "")))
        if not unit_id or unit_id == "None":
            raise ValueError("Every analysis unit must have a nonempty unit_id")
        if unit_id in seen:
            raise ValueError(f"Duplicate analysis unit: {unit_id}")
        seen.add(unit_id)
        value = finite_number(record.get("mean_ndvi"))
        valid = finite_number(record.get("valid_pixel_count", record.get("pixel_count")))
        vegetation = finite_number(record.get("vegetation_pixel_count", valid))
        vegetation_fraction = finite_number(record.get("vegetation_fraction"))
        if vegetation_fraction is None and valid is not None and valid > 0 and vegetation is not None:
            vegetation_fraction = vegetation / valid
        coverage = finite_number(record.get("coverage_fraction", record.get("valid_fraction")))
        total = finite_number(record.get("total_pixel_count"))
        if coverage is None and total is not None and total > 0 and valid is not None:
            coverage = valid / total
        if value is None or not -1 <= value <= 1 or valid is None or valid < minimum_pixels:
            continue
        if vegetation is None or vegetation <= 0 or vegetation > valid:
            continue
        if vegetation_fraction is None or not minimum_vegetation <= vegetation_fraction <= 1:
            continue
        if coverage is not None and not minimum_coverage <= coverage <= 1:
            continue
        if record.get("usable") is False or record.get("valid") is False or record.get("qa_usable") is False:
            continue
        record.update(unit_id=unit_id, mean_ndvi=value, valid_pixel_count=int(valid),
                      vegetation_pixel_count=int(vegetation), vegetation_fraction=vegetation_fraction)
        result.append(record)
    return sorted(result, key=lambda item: item["unit_id"])


def absolute_threshold(config: Mapping[str, Any] | None = None) -> float:
    options = anomaly_config(config)
    legacy = config_mapping(options, "thresholds")
    nested = config_mapping(options, "absolute")
    value = options.get("absolute_threshold", nested.get("threshold", legacy.get("ndvi_min")))
    return setting({"absolute_threshold": 0.35 if value is None else value},
                   "absolute_threshold", 0.35, minimum=-1, maximum=1)


def detect_absolute(
    records: Sequence[Mapping[str, Any]], config: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return method A candidates; the threshold is experimental, not diagnostic."""
    options = anomaly_config(config)
    threshold = absolute_threshold(options)
    scale = setting(options, "absolute_strength_scale", 0.2, minimum=1e-12)
    if not method_enabled(options, "absolute"):
        return []
    candidates = []
    for record in eligible_units(records, options):
        value = record["mean_ndvi"]
        if value < threshold:
            candidates.append({**record, "anomaly_type": "absolute", "method": "A",
                               "index_name": "NDVI", "observed_value": value,
                               "reference_value": threshold, "threshold": threshold,
                               "strength": min(1.0, (threshold - value) / scale),
                               "reason": f"Vegetation mean NDVI {value:.4f} is below the experimental threshold {threshold:.4f}; field inspection required."})
    return candidates
