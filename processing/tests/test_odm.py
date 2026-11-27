"""Technical ODM adapter tests; the container itself is mocked here."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from agriscan.mosaicking import odm_runner
from agriscan.mosaicking.mosaic_quality import MosaicQualityError, assess_mosaic, check_reconstruction
from agriscan.mosaicking.odm_runner import ODMError, run_odm


def raster(path, *, dtype="uint16", crs="EPSG:32648", alpha=False, hole=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 4 if alpha else 3
    height, width = 48, 64
    profile = {"driver": "GTiff", "height": height, "width": width, "count": count,
               "dtype": dtype, "transform": from_origin(600000, 1200000, 1, 1), "crs": crs}
    y, x = np.mgrid[:height, :width]
    maximum = 150 if dtype == "uint8" else 16000
    values = np.stack([(x + y + index * 3) % 100 + maximum for index in range(3)]).astype(dtype)
    with rasterio.open(path, "w", **profile) as image:
        image.write(values, indexes=(1, 2, 3))
        if alpha:
            valid = np.full((height, width), 65535, dtype=dtype)
            if hole:
                valid[:, :width // 2] = 0
            image.write(valid, 4)
    return values


@pytest.fixture
def inputs(tmp_path):
    directory = tmp_path / "input"
    directory.mkdir()
    positions = {}
    for index in range(3):
        path = directory / f"capture_{index:03}.tif"
        raster(path)
        # Distinct metadata makes each camera file unique, as in a capture.
        with rasterio.open(path, "r+") as image:
            image.update_tags(capture_id=str(index))
        positions[path.name] = {"longitude": 106.1 + index * .0001, "latitude": 10.7, "altitude": 30}
    return directory, positions


@pytest.fixture
def docker(monkeypatch, tmp_path):
    calls = []
    outcomes = []
    config = {"components": 1, "used": 3}
    monkeypatch.setattr(odm_runner.shutil, "which", lambda value: "/usr/bin/docker")

    def execute(command, **kwargs):
        calls.append(command)
        if command[1] == "info":
            return subprocess.CompletedProcess(command, 0, "25.0", "")
        if command[1] == "rm":
            return subprocess.CompletedProcess(command, 0)
        result = outcomes.pop(0) if outcomes else 0
        if isinstance(result, Exception):
            raise result
        if result:
            kwargs["stdout"].write("ODM failed: " + ("out of memory" if result == 137 else "no reconstruction") + "\n")
            kwargs["stdout"].flush()
            return subprocess.CompletedProcess(command, result)
        volume = command[command.index("--volume") + 1]
        project = Path(volume.rsplit(":", 1)[0]) / "survey"
        images = sorted(path.name for path in (project / "images").glob("*.tif"))
        recon = [{"shots": {name: {} for name in images[:config["used"]]}}]
        if config["components"] > 1:
            recon.append({"shots": {"isolated.tif": {}}})
        (project / "opensfm").mkdir(parents=True, exist_ok=True)
        (project / "opensfm" / "reconstruction.json").write_text(json.dumps(recon))
        raster(project / "odm_orthophoto" / "odm_orthophoto.tif", alpha=True, hole=True)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(odm_runner.subprocess, "run", execute)
    return calls, outcomes, config


def test_success_keeps_scale_spectral_values_and_alpha_mask(inputs, docker, tmp_path):
    directory, positions = inputs
    destination = tmp_path / "map.tif"
    report = run_odm(directory, tmp_path / "work", destination, config={}, positions=positions)
    assert report["reconstruction"]["used_image_ratio"] == 1
    assert report["quality"]["holes_verified"] is False
    assert Path(report["quality_path"]).is_file()
    with rasterio.open(destination) as image:
        assert image.count == 3
        assert image.dtypes == ("uint16",) * 3
        assert image.descriptions == ("red", "green", "nir")
        assert image.read(1)[10, 40] == 16050
        assert image.dataset_mask()[10, 0] == 0
        assert image.dataset_mask()[10, 40] == 255
        assert image.tags()["value_scale"] == "16384.0"
    calls = docker[0]
    command = next(command for command in calls if command[1] == "run")
    assert "opendronemap/odm:3.5.6" in command
    assert "--texturing-skip-global-seam-leveling" in command
    assert "--texturing-skip-local-seam-leveling" not in command
    assert command[command.index("--radiometric-calibration") + 1] == "none"
    assert command[command.index("--geo") + 1] == "/datasets/survey/geo.txt"
    assert any(command[1:3] == ["rm", "--force"] for command in calls)
    assert not destination.with_suffix(".tif.msk").exists()


def test_wgs84_camera_positions_are_written_correctly(inputs, docker, tmp_path):
    directory, positions = inputs
    run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)
    lines = (tmp_path / "work/survey/geo.txt").read_text().splitlines()
    assert lines[0] == "EPSG:4326"
    assert lines[1].split() == ["capture_000.tif", "106.1000000000", "10.7000000000", "30.0000"]


def test_missing_gps_never_invents_coordinates(inputs, docker, tmp_path):
    directory, _ = inputs
    with pytest.raises(ODMError, match="thiếu GPS") as error:
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={})
    assert error.value.code == "gps_missing"
    assert not any(command[1] == "run" for command in docker[0])


def test_duplicate_frames_fail_before_docker(inputs, docker, tmp_path):
    directory, positions = inputs
    paths = sorted(directory.glob("*.tif"))
    paths[1].write_bytes(paths[0].read_bytes())
    with pytest.raises(ODMError, match="trùng hệt"):
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)
    assert docker[0] == []


def test_uint8_input_is_not_quantitative(inputs, docker, tmp_path):
    directory, positions = inputs
    raster(directory / "capture_000.tif", dtype="uint8")
    with pytest.raises(ODMError, match="uint16"):
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)


def test_memory_retry_reduces_resources_once(inputs, docker, tmp_path):
    directory, positions = inputs
    docker[1].extend([137, 0])
    report = run_odm(directory, tmp_path / "work", tmp_path / "map.tif",
                     config={"max_concurrency": 4}, positions=positions)
    assert len(report["attempts"]) == 2
    command = [command for command in docker[0] if command[1] == "run"][1]
    assert command[command.index("--max-concurrency") + 1] == "1"
    assert command[command.index("--pc-quality") + 1] == "low"
    assert "--rerun-all" in command


def test_features_retry_is_bounded(inputs, docker, tmp_path):
    directory, positions = inputs
    docker[1].extend([1, 1, 1])
    with pytest.raises(ODMError, match="overlap") as error:
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif",
                config={"max_retries": 2}, positions=positions)
    assert error.value.code == "features"
    assert len([command for command in docker[0] if command[1] == "run"]) == 2
    assert len([command for command in docker[0] if command[1] == "rm"]) == 2


def test_timeout_removes_exact_container(inputs, docker, tmp_path):
    directory, positions = inputs
    docker[1].append(subprocess.TimeoutExpired(["docker", "run"], 1))
    with pytest.raises(ODMError, match="vượt quá") as error:
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif",
                config={"timeout_seconds": 1}, positions=positions)
    assert error.value.code == "timeout"
    command = next(command for command in docker[0] if command[1] == "run")
    name = command[command.index("--name") + 1]
    assert ["docker", "rm", "--force", name] in docker[0]


def test_disconnected_reconstruction_stops_alert_pipeline(inputs, docker, tmp_path):
    directory, positions = inputs
    docker[2]["components"] = 2
    with pytest.raises(ODMError, match="khối reconstruction") as error:
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)
    assert error.value.code == "quality_gate"
    assert not (tmp_path / "map.tif").exists()


def test_missing_camera_shots_stop_alert_pipeline(inputs, docker, tmp_path):
    directory, positions = inputs
    docker[2]["used"] = 2
    with pytest.raises(ODMError, match="2/3 ảnh"):
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)
    assert not (tmp_path / "map.tif").exists()


def test_runtime_missing_is_actionable(inputs, monkeypatch, tmp_path):
    directory, positions = inputs
    monkeypatch.setattr(odm_runner.shutil, "which", lambda value: None)
    with pytest.raises(ODMError, match="Chưa có Docker") as error:
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)
    assert error.value.code == "docker_missing"


def test_docker_daemon_failure_is_actionable(inputs, docker, monkeypatch, tmp_path):
    directory, positions = inputs
    monkeypatch.setattr(odm_runner.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, "", "permission denied"))
    with pytest.raises(ODMError, match="Docker daemon"):
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)


def test_latest_tag_is_rejected(inputs, docker, tmp_path):
    directory, positions = inputs
    with pytest.raises(ValueError, match="ghim phiên bản"):
        run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={"image": "opendronemap/odm:latest"}, positions=positions)


def test_repeated_workdir_is_rejected(inputs, docker, tmp_path):
    directory, positions = inputs
    work = tmp_path / "work"
    (work / "survey").mkdir(parents=True)
    with pytest.raises(ODMError, match="staging mới"):
        run_odm(directory, work, tmp_path / "map.tif", config={}, positions=positions)


def test_no_aoi_does_not_claim_hole_free_mosaic(tmp_path):
    path = tmp_path / "map.tif"
    raster(path, alpha=True, hole=True)
    report = assess_mosaic(path)
    assert report["valid_fraction_bbox"] == .5
    assert report["aoi_coverage"] is None
    assert report["holes_verified"] is False
    assert report["warnings"]


def write_aoi(path, right=600064):
    path.write_text(json.dumps({"type": "Polygon", "crs": {"type": "name", "properties": {"name": "EPSG:32648"}},
                                "coordinates": [[[600000, 1199952], [right, 1199952], [right, 1200000],
                                                  [600000, 1200000], [600000, 1199952]]]}))


def test_aoi_detects_nodata_hole(tmp_path):
    path, aoi = tmp_path / "map.tif", tmp_path / "aoi.geojson"
    raster(path, alpha=True, hole=True)
    write_aoi(aoi)
    with pytest.raises(MosaicQualityError, match="50.0% AOI"):
        assess_mosaic(path, boundary_path=aoi)


def test_aoi_outside_raster_is_counted_as_missing(tmp_path):
    path, aoi = tmp_path / "map.tif", tmp_path / "aoi.geojson"
    raster(path)
    write_aoi(aoi, right=600128)
    with pytest.raises(MosaicQualityError, match="50.0% AOI"):
        assess_mosaic(path, boundary_path=aoi)


def test_aoi_coverage_verified_with_complete_mosaic(tmp_path):
    path, aoi = tmp_path / "map.tif", tmp_path / "aoi.geojson"
    raster(path)
    write_aoi(aoi)
    report = assess_mosaic(path, boundary_path=aoi)
    assert report["aoi_coverage"] == 1
    assert report["holes_verified"] is True


@pytest.mark.parametrize("crs", [None, "EPSG:4326", "EPSG:2263"])
def test_invalid_or_nonmetric_crs_is_rejected(tmp_path, crs):
    path = tmp_path / "map.tif"
    raster(path, crs=crs)
    with pytest.raises(MosaicQualityError, match="CRS"):
        assess_mosaic(path)


def test_external_uint8_preview_rejected(tmp_path):
    path = tmp_path / "map.tif"
    raster(path, dtype="uint8")
    with pytest.raises(MosaicQualityError, match="8 bit"):
        assess_mosaic(path)


def test_cancel_removes_exact_container(inputs, docker, tmp_path):
    directory, positions = inputs
    # Simulate Ctrl+C after the running-container call has started.
    original = odm_runner.subprocess.run
    def interrupted(command, **kwargs):
        if command[1] == "run":
            docker[0].append(command)
            raise KeyboardInterrupt()
        return original(command, **kwargs)
    from unittest.mock import patch
    with patch.object(odm_runner.subprocess, "run", side_effect=interrupted):
        with pytest.raises(KeyboardInterrupt):
            run_odm(directory, tmp_path / "work", tmp_path / "map.tif", config={}, positions=positions)
    command = next(command for command in docker[0] if command[1] == "run")
    name = command[command.index("--name") + 1]
    assert ["docker", "rm", "--force", name] in docker[0]
