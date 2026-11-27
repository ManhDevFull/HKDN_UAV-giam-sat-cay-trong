"""RAW preparation with generated JPG EXIF and independent radiometric truth."""

from copy import deepcopy
import hashlib
import json

import numpy as np
from PIL import Image
import pytest
import tifffile

from agriscan.calibration import preprocess
from processing.radiometry import RelativeCorrector, load_settings


def write_jpeg(path, *, exposure=0.008, gps=True, gps_changes=None, model="Survey3W_RGN", size=(4, 4), timestamp=None):
    exif = Image.Exif()
    exif[271], exif[272] = "MAPIR", model
    exif[34665] = {33434: exposure, 34855: 100}
    if timestamp is not None:
        exif[34665][36867] = timestamp
    if gps:
        values = {1: "N", 2: (10.0, 30.0, 0.0), 3: "E", 4: (107.0, 15.0, 0.0), 5: 0, 6: 20.0}
        values.update(gps_changes or {})
        exif[34853] = values
    Image.new("RGB", size, (50, 100, 150)).save(path, exif=exif)
    return path


@pytest.fixture
def generated_survey(tmp_path, monkeypatch):
    source = tmp_path / "survey"
    raw_dir = source / "raw"
    raw_dir.mkdir(parents=True)
    settings = load_settings()
    settings["raw_black_level"] = 16
    # Three bands have different attenuations. Their post-correction reference
    # DN truth is R=400, G=1600, NIR=1600, yielding NDVI=0.6.
    profile = {"profile_id": "synthetic-constant-flat", "sensor_shape": [4, 4],
               "channels": {color: {"coefficients": [[attenuation]], "validation": {"scope": "synthetic only"}}
                            for color, attenuation in (("R", 0.5), ("G", 0.25), ("B", 1.0))}}
    arrays = {}
    exposures = (0.004, 0.008, 0.006)
    for index, exposure in enumerate(exposures):
        path = raw_dir / f"capture-{index}.RAW"
        path.write_bytes(f"synthetic RAW decoder input {index}".encode())
        ratio = exposure / 0.008
        mosaic = np.empty((4, 4), dtype=np.uint16)
        mosaic[0::2, 0::2] = 16 + 400 * 0.5 * ratio
        mosaic[0::2, 1::2] = mosaic[1::2, 0::2] = 16 + 1600 * 0.25 * ratio
        mosaic[1::2, 1::2] = 16 + 1600 * ratio
        arrays[path] = mosaic
        write_jpeg(path.with_suffix(".JPG"), exposure=exposure,
                   gps_changes={4: (107.0, 15.0, float(index))})

    def read_raw(path, *, survey_metadata):
        mosaic = arrays[path].copy()
        return mosaic, {"cfa_pattern": "RGGB", "white_level": 4095,
                        "pixel_stats": {"saturated_ratio": float(np.count_nonzero(mosaic >= 4095) / mosaic.size)}}

    monkeypatch.setattr(preprocess, "read_raw", read_raw)
    monkeypatch.setattr(preprocess, "load_settings", lambda: deepcopy(settings))
    monkeypatch.setattr(preprocess, "RelativeCorrector", lambda supplied: RelativeCorrector(supplied, lens_profile=profile))
    metadata = {"camera": {"model": "Survey3W", "filter": "RGN"}}
    config = {"mosaicking": {"common_scale": 4095, "min_images": 3}}
    return source, arrays, metadata, config


def test_factory_exposure_and_black_correction_share_one_fixed_scale(generated_survey, tmp_path):
    source, arrays, metadata, config = generated_survey
    original = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (source / "raw").iterdir()}
    result = preprocess.prepare_images(source, tmp_path / "prepared", metadata, config)
    assert result["report"]["prepared_count"] == 3
    assert result["report"]["rejected_count"] == 0
    assert len(result["positions"]) == 3
    assert len({position["longitude"] for position in result["positions"].values()}) == 3
    expected = np.tile(np.array([400, 1600, 1600], dtype=np.uint16), (2, 2, 1))
    for path in sorted(result["image_dir"].glob("*.tif")):
        encoded = tifffile.imread(path)
        assert encoded.dtype == np.uint16
        np.testing.assert_array_equal(encoded, expected)
        red, nir = encoded[:, :, 0].astype(float), encoded[:, :, 2].astype(float)
        np.testing.assert_allclose((nir - red) / (nir + red), 0.6)
        with tifffile.TiffFile(path) as image:
            description = json.loads(image.pages[0].description)
            assert description["scale"] == 4095
            assert description["bands"] == ["red", "green", "nir"]
            assert description["units"] == "relative_signal"
    for record in result["report"]["records"]:
        assert record["correction"]["factory_flat_applied"] is True
        assert record["correction"]["exposure_normalized"] is True
        assert record["joint_valid_fraction"] == 1
    assert result["report"]["analysis_eligibility"] == {"absolute_reflectance": False, "cross_survey_comparison": False}
    assert result["report"]["capture_day_consistency"] == "unverified"
    assert original == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in original}


@pytest.mark.parametrize("with_jpg", [False, True])
def test_missing_gps_never_gets_invented(generated_survey, tmp_path, with_jpg):
    source, _, metadata, config = generated_survey
    for path in (source / "raw").glob("*.JPG"):
        if with_jpg:
            write_jpeg(path, gps=False)
        else:
            path.unlink()
    target = tmp_path / "prepared"
    with pytest.raises(ValueError, match="Only 0 usable geotagged RAW"):
        preprocess.prepare_images(source, target, metadata, config)
    report = json.loads((target / "preprocessing.json").read_text())
    assert report["prepared_count"] == 0
    assert report["rejected_count"] == 3
    assert {record["reason"] for record in report["rejected"]} == {"missing_valid_GPS"}
    assert not list((target / "images").iterdir())


def test_signal_and_saturation_rejections_are_explicit(generated_survey, tmp_path):
    source, arrays, metadata, config = generated_survey
    paths = sorted(arrays)
    arrays[paths[0]][:] = 16  # black only
    arrays[paths[1]][:] = 4095  # every channel saturated
    target = tmp_path / "prepared"
    with pytest.raises(ValueError, match="Only 1 usable"):
        preprocess.prepare_images(source, target, metadata, config)
    report = json.loads((target / "preprocessing.json").read_text())
    assert report["prepared_count"] == 1
    assert report["rejected_count"] == 2
    assert {record["reason"] for record in report["rejected"]} == {"unusable_signal"}
    assert {flag for record in report["rejected"] for flag in record["quality_flags"]} == {"low_signal", "no_valid_pixels"}


def test_partial_saturation_uses_zero_for_all_bands_and_retains_qa(generated_survey, tmp_path):
    source, arrays, metadata, config = generated_survey
    arrays[sorted(arrays)[0]][0, 0] = 4095
    result = preprocess.prepare_images(source, tmp_path / "prepared", metadata, config)
    first = result["report"]["records"][0]
    assert first["joint_valid_fraction"] == 0.75
    assert first["sensor_saturation_fraction"] == 1 / 16
    encoded = tifffile.imread(result["image_dir"] / first["odm_image"])
    np.testing.assert_array_equal(encoded[0, 0], [0, 0, 0])
    np.testing.assert_array_equal(encoded[1, 1], [400, 1600, 1600])
    assert any("interpolation" in warning for warning in first["warnings"])


def test_overflow_is_rejected_instead_of_per_image_rescaling(generated_survey, tmp_path):
    source, _, metadata, config = generated_survey
    config["mosaicking"]["common_scale"] = 65535 * 3
    target = tmp_path / "prepared"
    with pytest.raises(ValueError, match="Only 0 usable"):
        preprocess.prepare_images(source, target, metadata, config)
    report = json.loads((target / "preprocessing.json").read_text())
    assert all(record["reason"].startswith("common_scale_overflow") for record in report["rejected"])
    assert not list((target / "images").iterdir())


def test_usable_images_from_different_capture_days_must_be_split(generated_survey, tmp_path):
    source, _, metadata, config = generated_survey
    for index, path in enumerate(sorted((source / "raw").glob("*.JPG"))):
        day = "03" if index == 1 else "02"
        write_jpeg(path, timestamp=f"2026:11:{day} 12:00:00")
    with pytest.raises(ValueError, match="multiple capture days"):
        preprocess.prepare_images(source, tmp_path / "prepared", metadata, config)


def test_verified_survey_filename_supplies_capture_day_without_inventing_it(generated_survey, tmp_path):
    source, arrays, metadata, config = generated_survey
    for index, path in enumerate(sorted(arrays)):
        renamed = path.with_name(f"2026_1102_04110{index}_{index + 1:03}.RAW")
        path.rename(renamed)
        path.with_suffix(".JPG").rename(renamed.with_suffix(".JPG"))
        arrays[renamed] = arrays.pop(path)
    result = preprocess.prepare_images(source, tmp_path / "prepared", metadata, config)
    assert result["report"]["capture_days"] == ["2026-11-02"]
    assert result["report"]["capture_day_consistency"] == "verified_single_day"
    assert result["report"]["warnings"] == []


@pytest.mark.parametrize("filter_name", ["RGB", "OCN", "UNKNOWN"])
def test_camera_filter_must_be_explicitly_rgn(generated_survey, tmp_path, filter_name):
    source, _, metadata, config = generated_survey
    metadata["camera"]["filter"] = filter_name
    with pytest.raises(ValueError, match="RGN"):
        preprocess.prepare_images(source, tmp_path / "prepared", metadata, config)


def test_gps_round_trip_sign_altitude_and_malformed_tags(tmp_path):
    path = tmp_path / "gps.JPG"
    write_jpeg(path)
    assert preprocess._gps(path) == {"longitude": 107.25, "latitude": 10.5, "altitude": 20.0}
    write_jpeg(path, gps_changes={1: "S", 3: "W", 5: 1})
    assert preprocess._gps(path) == {"longitude": -107.25, "latitude": -10.5, "altitude": -20.0}
    for changes in ({1: "X"}, {3: "X"}, {2: (10.0, 60.0, 0.0)}, {4: (181.0, 0.0, 0.0)}, {5: 2}, {2: (0.0, 0.0, 0.0), 4: (0.0, 0.0, 0.0)}):
        write_jpeg(path, gps_changes=changes)
        assert preprocess._gps(path) is None
    path.write_bytes(b"corrupt jpeg")
    assert preprocess._gps(path) is None
    assert preprocess._gps(tmp_path / "missing.JPG") is None
