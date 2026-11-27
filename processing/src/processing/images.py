"""JPEG input and conservative RAW/JPEG association without copying private EXIF.

JPEGs retain their camera encoded values. A processed JPEG cannot establish
linear radiance or absolute reflectance without a measured camera response.
"""

from datetime import datetime
import math
from pathlib import Path
import re

import numpy as np
from PIL import Image


_SURVEY_NAME = re.compile(r"^(\d{4}_\d{4}_\d{6})_(\d+)$")


def _filename_capture(path: Path) -> tuple[datetime, int] | None:
    match = _SURVEY_NAME.fullmatch(path.stem)
    if match is None:
        return None
    try:
        return datetime.strptime(match[1], "%Y_%m%d_%H%M%S"), int(match[2])
    except ValueError:
        return None


def _positive_number(value: object) -> float | None:
    if isinstance(value, (tuple, list)):
        value = value[0] if value else None
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, ZeroDivisionError, OverflowError):
        return None
    return result if math.isfinite(result) and result > 0 else None


def _text(value: object) -> str | None:
    return value.rstrip("\x00").strip()[:256] if isinstance(value, str) else None


def _metadata(image: Image.Image, path: Path) -> dict[str, object]:
    # Explicit allowlist: GPS, serial numbers, MakerNote and arbitrary EXIF are
    # never exported to the processing metadata or downstream manifests.
    warnings = [
        "JPEG values are camera processed; transfer function is unknown. "
        "Do not interpret them as linear RAW or absolute reflectance.",
        "G1 and G2 are duplicate JPEG green averages, not independent CFA samples.",
    ]
    try:
        exif = image.getexif()
        sub = exif.get_ifd(34665) if 34665 in exif else {}
    except (KeyError, TypeError, ValueError, OSError, SyntaxError):
        exif, sub = {}, {}
        warnings.append("JPEG EXIF could not be read; exposure and capture time are unknown.")
    original = _text(sub.get(36867, exif.get(36867)))
    timestamp = None
    timestamp_status = "absent"
    if original:
        try:
            timestamp = datetime.strptime(original, "%Y:%m:%d %H:%M:%S").isoformat()
            timestamp_status = "valid"
        except ValueError:
            timestamp_status = "invalid"
            warnings.append("JPEG DateTimeOriginal is malformed; automatic timestamp pairing is disabled.")
    orientation = exif.get(274)
    if not isinstance(orientation, int) or not 1 <= orientation <= 8:
        orientation = None
    if orientation not in (None, 1):
        warnings.append("EXIF orientation is recorded without rotating pixels, preserving RAW alignment.")
    exposure = _positive_number(sub.get(33434, exif.get(33434)))
    iso = _positive_number(sub.get(34855, exif.get(34855)))
    return {
        "source": path.name,
        "decoder": "pillow-jpeg",
        "width": image.width,
        "height": image.height,
        "pattern": None,
        "units": "jpeg_encoded_DN",
        "transfer": "camera_processed_unknown",
        "bit_depth": 8,
        "white_level": 255,
        "white_level_source": "JPEG encoding limit; not a measured sensor saturation threshold",
        "black_levels": None,
        "exposure_seconds": exposure,
        "iso": int(iso) if iso is not None and iso.is_integer() else iso,
        "datetime_original": timestamp,
        "timestamp_status": timestamp_status,
        "orientation": orientation,
        "make": _text(exif.get(271)),
        "model": _text(exif.get(272)),
        "warnings": warnings,
    }


def read_jpeg(path: Path) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Return native-orientation, half-resolution R/G1/G2/B encoded DN planes.

Each plane is the mean of the corresponding JPEG RGB component in a 2x2
block. Green is copied into G1 and G2 for the shared output interface.
Images with odd dimensions are rejected rather than silently cropping.
"""
    path = Path(path)
    try:
        with Image.open(path) as image:
            if image.format != "JPEG":
                raise ValueError(f"{path.name}: expected JPEG encoded input")
            if image.width % 2 or image.height % 2:
                raise ValueError(f"{path.name}: JPEG width and height must be even")
            metadata = _metadata(image, path)
            pixels = np.asarray(image.convert("RGB"), dtype=np.float32)
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"{path.name}: cannot decode JPEG ({exc})") from exc
    height, width = pixels.shape[:2]
    reduced = pixels.reshape(height // 2, 2, width // 2, 2, 3).mean(axis=(1, 3))
    planes = {
        "R": reduced[:, :, 0].copy(),
        "G1": reduced[:, :, 1].copy(),
        "G2": reduced[:, :, 1].copy(),
        "B": reduced[:, :, 2].copy(),
    }
    return planes, metadata


def read_jpeg_metadata(path: Path) -> dict[str, object]:
    """Read only allowlisted EXIF and dimensions, without decoding pixel data."""
    path = Path(path)
    try:
        with Image.open(path) as image:
            if image.format != "JPEG":
                raise ValueError(f"{path.name}: expected JPEG encoded input")
            return _metadata(image, path)
    except (OSError, SyntaxError, ValueError):
        raise ValueError(f"{path.name}: cannot read JPEG metadata") from None


def _timestamp_consistent(metadata: dict[str, object], raw_time: datetime | None,
                          jpeg_time: datetime | None, max_delta: float) -> bool:
    if metadata["timestamp_status"] == "invalid":
        return False
    timestamp = metadata["datetime_original"]
    if timestamp is None:
        return True
    capture = datetime.fromisoformat(str(timestamp))
    if raw_time is not None and jpeg_time is not None and jpeg_time != raw_time:
        return raw_time <= capture <= jpeg_time
    anchor = raw_time if raw_time is not None else jpeg_time
    return anchor is None or abs((capture - anchor).total_seconds()) <= max_delta


def pair_jpegs(raw_paths: list[Path], jpeg_paths: list[Path], max_delta_seconds: float = 3.0
               ) -> tuple[dict[Path, Path], list[Path], dict[Path, str]]:
    """Associate only unique same-directory RAW/JPEG captures, preferring stems.

Fallback Survey3 association requires a valid YYYY_MMDD_HHMMSS_NNN name,
JPEG sequence = RAW sequence + 1, and JPEG time 0..max_delta_seconds after
RAW time. Available EXIF DateTimeOriginal must agree with that interval.
Any RAW with multiple candidates, or any JPEG claimed by multiple RAWs,
is left unpaired. Exact-stem candidates have priority over fallback names.

Returns (RAW -> JPEG, sorted unmatched JPEGs, reason for every RAW). Reasons
are exact_stem, survey3_sequence_timestamp, no_matching_jpeg, or
ambiguous_jpeg_candidates. Paths retain the caller's absolute/relative form.
"""
    if isinstance(max_delta_seconds, bool) or not math.isfinite(max_delta_seconds) or max_delta_seconds < 0:
        raise ValueError("max_delta_seconds must be finite and nonnegative")
    raws = sorted(set(map(Path, raw_paths)))
    jpegs = sorted(set(map(Path, jpeg_paths)))
    headers = {}
    for path in jpegs:
        try:
            headers[path] = read_jpeg_metadata(path)
        except ValueError:
            headers[path] = None
    captures = {path: _filename_capture(path) for path in raws + jpegs}
    pairs: dict[Path, Path] = {}
    reasons = {path: "no_matching_jpeg" for path in raws}
    ambiguous: set[Path] = set()

    def accept_unique(candidates: dict[Path, list[Path]], method: str) -> None:
        claims: dict[Path, list[Path]] = {}
        for raw, matches in candidates.items():
            for jpeg in matches:
                claims.setdefault(jpeg, []).append(raw)
        for raw, matches in candidates.items():
            if len(matches) == 1 and len(claims[matches[0]]) == 1:
                pairs[raw] = matches[0]
                reasons[raw] = method
            elif matches:
                ambiguous.add(raw)
                reasons[raw] = "ambiguous_jpeg_candidates"

    exact: dict[Path, list[Path]] = {}
    for raw in raws:
        raw_capture = captures[raw]
        exact[raw] = [jpeg for jpeg in jpegs
                      if jpeg.parent == raw.parent and jpeg.stem == raw.stem
                      and headers[jpeg] is not None
                      and _timestamp_consistent(headers[jpeg],
                                                raw_capture[0] if raw_capture else None,
                                                raw_capture[0] if raw_capture else None,
                                                max_delta_seconds)]
    accept_unique(exact, "exact_stem")
    # Reserve even ambiguous exact matches: fallback must never consume them.
    reserved = {jpeg for matches in exact.values() for jpeg in matches}
    fallback: dict[Path, list[Path]] = {}
    for raw in raws:
        if raw in pairs or raw in ambiguous or captures[raw] is None:
            continue
        raw_time, raw_sequence = captures[raw]
        matches = []
        for jpeg in jpegs:
            if (jpeg in reserved or jpeg.parent != raw.parent or captures[jpeg] is None
                    or headers[jpeg] is None):
                continue
            jpeg_time, jpeg_sequence = captures[jpeg]
            delta = (jpeg_time - raw_time).total_seconds()
            if (jpeg_sequence == raw_sequence + 1 and 0 <= delta <= max_delta_seconds
                    and _timestamp_consistent(headers[jpeg], raw_time, jpeg_time, max_delta_seconds)):
                matches.append(jpeg)
        fallback[raw] = matches
    accept_unique(fallback, "survey3_sequence_timestamp")
    used = set(pairs.values())
    return pairs, [jpeg for jpeg in jpegs if jpeg not in used], reasons
