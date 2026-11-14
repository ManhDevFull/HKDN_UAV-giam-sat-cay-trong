"""Linear panel calibration and independent repeat-capture quality checks.

Reflectance is a fraction: 0.5 means 50 percent. Calibration uses linear,
vignetting-corrected channel values, without display normalization or gamma.
"""

from collections.abc import Mapping

import numpy as np


CHANNELS = ("R", "G1", "G2", "B")
_METRIC = "100 * (max - min) / mean across expected sessions"


def _vector(values: object, label: str) -> np.ndarray:
    try:
        result = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must contain numeric values") from error
    if result.ndim != 1 or result.size < 2:
        raise ValueError(f"{label} must contain at least two values")
    if not np.isfinite(result).all():
        raise ValueError(f"{label} must contain only finite values")
    return result


def fit_empirical_line(
    samples: dict[str, list[float]], references: dict[str, list[float]]
) -> dict[str, dict]:
    """Fit ``reflectance = gain * DN + offset`` independently per channel.

    Each value is the mean of one panel ROI; corresponding reference values
    must come from that panel's calibration certificate for the same band.
    A zero-reflectance reference is permitted. At least two different panel
    values are required, and the fitted response must increase with DN.
    """
    if not isinstance(samples, Mapping) or not isinstance(references, Mapping):
        raise ValueError("samples and references must be channel mappings")
    if not samples or set(samples) != set(references):
        raise ValueError("samples and references must have the same nonempty channels")
    if set(samples).difference(CHANNELS):
        raise ValueError(f"supported channels are {', '.join(CHANNELS)}")

    result: dict[str, dict] = {}
    for channel in CHANNELS:
        if channel not in samples:
            continue
        raw = _vector(samples[channel], f"{channel} samples")
        reflectance = _vector(references[channel], f"{channel} references")
        if raw.size != reflectance.size:
            raise ValueError(f"{channel}: sample and reference counts differ")
        if np.any((reflectance < 0) | (reflectance > 1)):
            raise ValueError(f"{channel}: reference reflectances must be in [0, 1]")
        if np.ptp(reflectance) <= np.finfo(np.float64).eps:
            raise ValueError(f"{channel}: reference reflectances must differ")

        # Center and scale DN before least squares: a large camera offset must
        # not make an otherwise valid two-panel system numerically singular.
        with np.errstate(over="ignore", invalid="ignore"):
            center = float(np.mean(raw))
            centered = raw - center
            scale = float(np.max(np.abs(centered)))
        tolerance = 16 * np.finfo(np.float64).eps * max(1.0, float(np.max(np.abs(raw))))
        if not np.isfinite(center) or not np.isfinite(scale) or scale <= tolerance:
            raise ValueError(f"{channel}: raw panel values are identical or too close")
        design = np.column_stack((centered / scale, np.ones(raw.size)))
        fitted, _, rank, _ = np.linalg.lstsq(design, reflectance, rcond=None)
        gain = float(fitted[0] / scale)
        offset = float(fitted[1] - gain * center)
        if rank != 2 or not np.isfinite([gain, offset]).all() or gain <= 0:
            raise ValueError(f"{channel}: calibration must have a finite positive gain")
        residual = design @ fitted - reflectance
        result[channel] = {
            "gain": gain,
            "offset": offset,
            "rmse": float(np.sqrt(np.mean(residual * residual))),
            "sample_count": int(raw.size),
        }
    return result


def apply_reflectance(image: np.ndarray, coefficients: dict) -> np.ndarray:
    """Apply one channel's gain/offset, preserving NaNs and unclipped values.

    Negative values or values above 1 remain visible for quality review. The
    input array is never modified; output values are linear float32 fractions.
    """
    try:
        gain = float(coefficients["gain"])
        offset = float(coefficients["offset"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("coefficients must contain numeric gain and offset") from error
    if not np.isfinite([gain, offset]).all() or gain <= 0:
        raise ValueError("gain must be finite and positive; offset must be finite")
    with np.errstate(over="ignore", invalid="ignore"):
        return (np.asarray(image, dtype=np.float64) * gain + offset).astype(np.float32)


def _status(statuses: list[str]) -> str:
    if "failed" in statuses:
        return "failed"
    if not statuses or "incomplete" in statuses:
        return "incomplete"
    return "passed"


def validate_timepoints(
    records: list[dict], expected_sessions: list[str], threshold_percent: float = 5.0
) -> dict:
    """Check independent ROIs of the same object in at least three sessions.

    ``records`` contain ``session``, ``object_id`` and calibrated ``means`` for
    R/G1/G2/B. They must be validation objects, not the panel values used to fit
    the model. A channel passes only if its relative spread is strictly below
    the threshold; incomplete sessions cannot pass. This measures repeatability,
    not absolute accuracy against a certified reflectance target.
    """
    try:
        threshold = float(threshold_percent)
    except (TypeError, ValueError) as error:
        raise ValueError("threshold_percent must be finite and positive") from error
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold_percent must be finite and positive")
    if any(not isinstance(session, str) or not session.strip() for session in expected_sessions):
        raise ValueError("expected session names must be nonempty strings")
    # Retain order while counting distinct slots. A repeated name cannot stand
    # in for another independent capture.
    sessions = list(dict.fromkeys(expected_sessions))
    report: dict = {
        "status": "incomplete",
        "metric": _METRIC,
        "threshold_percent": threshold,
        "expected_sessions": sessions,
        "objects": {},
    }
    grouped: dict[str, dict[str, dict]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError("each validation record must be a mapping")
        session = record.get("session")
        object_id = record.get("object_id")
        if not isinstance(session, str) or not session.strip():
            raise ValueError("each record needs a nonempty session name")
        if not isinstance(object_id, str) or not object_id.strip():
            raise ValueError("each record needs a nonempty object_id")
        object_records = grouped.setdefault(object_id, {})
        if session in object_records:
            raise ValueError(f"duplicate validation record: {object_id}/{session}")
        object_records[session] = record

    if len(sessions) < 3:
        report["reason"] = "at least three distinct expected sessions are required"
        return report
    if not grouped:
        report["reason"] = "no independent validation measurements were supplied"
        return report

    for object_id, object_records in grouped.items():
        object_report: dict = {"channels": {}}
        unexpected = sorted(set(object_records).difference(sessions))
        object_issues: list[str] = []
        if unexpected:
            object_issues.append(f"unexpected sessions: {', '.join(unexpected)}")
        for session in sessions:
            if session not in object_records:
                continue
            means = object_records[session].get("means")
            if isinstance(means, Mapping):
                extras = set(means).difference(CHANNELS)
                if extras:
                    object_issues.append(f"{session}: unsupported channel names")
            else:
                object_issues.append(f"{session}: means must be a channel mapping")

        for channel in CHANNELS:
            values: dict[str, float] = {}
            missing: list[str] = []
            invalid: list[str] = []
            for session in sessions:
                means = object_records.get(session, {}).get("means", {})
                if not isinstance(means, Mapping) or channel not in means:
                    missing.append(session)
                    continue
                try:
                    value = float(means[channel])
                except (TypeError, ValueError):
                    invalid.append(session)
                    continue
                if not np.isfinite(value) or not 0 <= value <= 1:
                    invalid.append(session)
                    continue
                values[session] = value
            channel_report: dict = {
                "status": "incomplete",
                "values": values,
                "relative_spread_percent": None,
            }
            if invalid:
                channel_report.update(
                    status="failed", reason=f"invalid reflectance in: {', '.join(invalid)}"
                )
            elif missing:
                channel_report["reason"] = f"missing measurements in: {', '.join(missing)}"
            else:
                measured = np.asarray(list(values.values()), dtype=np.float64)
                mean = float(np.mean(measured))
                if mean <= 0:
                    channel_report.update(status="failed", reason="mean must be positive")
                else:
                    spread = float(100.0 * np.ptp(measured) / mean)
                    channel_report["relative_spread_percent"] = spread
                    channel_report["status"] = "passed" if spread < threshold else "failed"
                    if channel_report["status"] == "failed":
                        channel_report["reason"] = "relative spread must be below threshold"
            object_report["channels"][channel] = channel_report

        statuses = [item["status"] for item in object_report["channels"].values()]
        if object_issues:
            object_report["issues"] = object_issues
            statuses.append("failed")
        object_report["status"] = _status(statuses)
        report["objects"][object_id] = object_report
    report["status"] = _status([item["status"] for item in report["objects"].values()])
    return report
