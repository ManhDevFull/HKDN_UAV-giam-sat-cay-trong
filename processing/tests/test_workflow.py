"""Full GIS workflow checks, with only RAW decoding/ODM boundaries mocked."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest
import rasterio

from agriscan import cli
from agriscan.mosaicking.odm_runner import ODMError
from agriscan.pipeline import runner
from agriscan.pipeline.demo import create_demo_mosaic


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from all_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from all_strings(item)


def assert_artifacts(target):
    manifest = load_json(target / "manifest.json")
    for name, path in manifest["paths"].items():
        assert not Path(path).is_absolute(), (name, path)
        assert (target / path).is_file(), (name, path)
    assert (target / manifest["summary"]).is_file()
    assert (target / manifest["config"]).is_file()
    for path in target.rglob("*.json"):
        assert not any(".work-" in item for item in all_strings(load_json(path))), path
    return manifest


def test_demo_computes_gis_masks_statistics_and_both_alert_methods(tmp_path):
    target = tmp_path / "demo"
    report = runner.run_demo(output_dir=target)
    assert report["analysis_eligibility"]["synthetic"] is True
    assert report["source"]["odm_executed"] is False
    assert report["grid_unit_count"] == 80
    assert report["pixel_counts"]["shadow_pixel_count"] == 1000
    assert report["pixel_counts"]["bare_soil_pixel_count"] == 1000
    assert report["anomalies"]["method_a_count"] > 0
    assert report["anomalies"]["method_b_count"] > 0
    manifest = assert_artifacts(target)
    with rasterio.open(target / manifest["paths"]["ndvi"]) as ndvi, \
            rasterio.open(target / manifest["paths"]["orthomosaic"]) as mosaic:
        assert ndvi.crs == mosaic.crs
        assert ndvi.transform == mosaic.transform
        assert ndvi.read(1)[20, 20] == pytest.approx(.25, abs=.02)
    alerts = load_json(target / manifest["paths"]["alerts_geojson"])
    priorities = [feature["properties"]["priority_rank"] for feature in alerts["features"]]
    assert priorities == list(range(1, len(priorities) + 1))
    assert not list(tmp_path.glob(".demo.work-*"))


@pytest.fixture
def mocked_raw(monkeypatch, tmp_path):
    source = tmp_path / "survey"
    source.mkdir()
    marker = source / "immutable.raw"
    marker.write_bytes(b"source must stay immutable")
    calls = []
    validation = {"is_valid": True, "errors": [], "counts": {"raw_count": 3, "jpg_count": 3}}
    monkeypatch.setattr(runner, "validate_survey_folder", lambda path: validation)
    monkeypatch.setattr(runner, "read_metadata", lambda path: {"survey_id": "s-001", "plot_id": "p-001"})

    def prepare(survey_dir, output_dir, metadata, config):
        images = output_dir / "images"
        images.mkdir(parents=True)
        report = {"prepared_count": 3, "rejected_count": 0, "records": []}
        (output_dir / "preprocessing.json").write_text(json.dumps(report))
        return {"image_dir": images, "positions": {}, "report": report}

    def odm(image_dir, work_dir, output_path, *, config, positions, boundary_path):
        calls.append((image_dir, work_dir, config))
        work_dir.mkdir()
        float_source = work_dir / "synthetic.tif"
        create_demo_mosaic(float_source)
        output_path.parent.mkdir(parents=True)
        with rasterio.open(float_source) as image:
            values = image.read()
            valid = image.dataset_mask() > 0
            profile = image.profile.copy()
            profile.update(dtype="uint16", nodata=None)
            encoded = np.rint(np.where(valid, values, 0) * config["common_scale"]).astype("uint16")
            with rasterio.Env(GDAL_TIFF_INTERNAL_MASK=True), rasterio.open(output_path, "w", **profile) as target:
                target.write(encoded)
                target.write_mask(valid.astype("uint8") * 255)
        log = work_dir / "odm-attempt-1.log"
        log.write_text("Mock ODM boundary only; spectral maps use the real GIS pipeline.\n")
        return {"orthomosaic": str(output_path), "native_orthomosaic": str(float_source),
                "quality_path": str(work_dir / "mosaic-quality.json"),
                "log_path": str(log), "attempts": [{"attempt": 1, "log": str(log)}],
                "quality": {"path": str(output_path), "valid_fraction_bbox": .99,
                            "holes_verified": False},
                "reconstruction": {"used_image_ratio": 1, "used_images": 3, "input_images": 3}}

    monkeypatch.setattr(runner, "prepare_images", prepare)
    monkeypatch.setattr(runner, "run_odm", odm)
    return source, marker, calls


def test_raw_boundary_integration_normalizes_shared_scale_and_exports(tmp_path, mocked_raw):
    source, marker, calls = mocked_raw
    target = tmp_path / "result"
    report = runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)
    assert report["status"] == "completed"
    assert report["analysis_eligibility"]["synthetic"] is False
    assert calls[0][2]["common_scale"] == 16384
    manifest = assert_artifacts(target)
    with rasterio.open(target / manifest["paths"]["orthomosaic"]) as image:
        assert image.count == 3
        assert image.dtypes == ("float32",) * 3
        assert image.read(3)[15, 50] == pytest.approx(.55, abs=.01)
        assert image.read(1, masked=True).mask[-1, -1]
        assert image.tags()["units"] == "relative_signal"
    assert not (target / "maps/orthomosaic_dn.tif").exists()
    assert (target / "logs/odm-attempt-1.log").is_file()
    assert marker.read_bytes() == b"source must stay immutable"
    assert not list(tmp_path.glob(".result.work-*"))


def test_odm_failure_preserves_last_output_and_captures_log_before_cleanup(tmp_path, mocked_raw, monkeypatch):
    source, marker, _ = mocked_raw
    target = tmp_path / "result"
    runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)
    old_summary = (target / "summary.json").read_bytes()
    old_mosaic = (target / "maps/orthomosaic.tif").read_bytes()

    def fail(image_dir, work_dir, output_path, **kwargs):
        work_dir.mkdir()
        log = work_dir / "odm-attempt-1.log"
        log.write_text("REAL_DIAGNOSTIC: not enough overlapping images\n")
        raise ODMError("Disconnected reconstruction", code="quality_gate", log_path=log)

    monkeypatch.setattr(runner, "run_odm", fail)
    with pytest.raises(runner.WorkflowError, match="Disconnected"):
        runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)
    failure = load_json(tmp_path / "result.failure.json")
    assert failure["phase"] == "odm"
    assert failure["code"] == "quality_gate"
    assert "REAL_DIAGNOSTIC" in failure["odm_log_tail"]
    assert failure["previous_output_preserved"] is True
    assert (target / "summary.json").read_bytes() == old_summary
    assert (target / "maps/orthomosaic.tif").read_bytes() == old_mosaic
    assert marker.read_bytes() == b"source must stay immutable"
    assert not list(tmp_path.glob(".result.work-*"))


def test_success_clears_owned_failure_report(tmp_path, mocked_raw):
    source, _, _ = mocked_raw
    target = tmp_path / "result"
    failure = tmp_path / "result.failure.json"
    failure.write_text(json.dumps({"tool": "agriscan-workflow", "status": "failed"}))
    runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)
    assert not failure.exists()


def test_raw_command_requires_experimental_ack_before_any_mutation(tmp_path, mocked_raw, monkeypatch, capsys):
    source, _, calls = mocked_raw
    target = tmp_path / "result"
    monkeypatch.setattr(sys, "argv", ["agriscan", "process", "--input", str(source), "--output", str(target)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert "--experimental" in capsys.readouterr().err
    assert calls == []
    assert not target.exists()


def test_cli_run_alias_calls_complete_workflow(tmp_path, mocked_raw, monkeypatch, capsys):
    source, _, calls = mocked_raw
    target = tmp_path / "result"
    monkeypatch.setattr(sys, "argv", ["agriscan", "run", "--input", str(source), "--output", str(target), "--experimental"])
    cli.main()
    assert len(calls) == 1
    assert "Completed:" in capsys.readouterr().out
    assert_artifacts(target)


def test_existing_mosaic_units_gate_and_source_immutable(tmp_path):
    mosaic = tmp_path / "linear.tif"
    create_demo_mosaic(mosaic)
    with rasterio.open(mosaic, "r+") as image:
        image.update_tags(synthetic="false")
    before = mosaic.read_bytes()
    target = tmp_path / "analysis"
    report = runner.analyze_existing(mosaic, survey_id="s", plot_id="p", output_dir=target, experimental=True)
    assert report["source"]["odm_reconstruction_verified"] is False
    assert mosaic.read_bytes() == before
    assert_artifacts(target)
    old = (target / "manifest.json").read_bytes()
    with rasterio.open(mosaic, "r+") as image:
        image.update_tags(units="unverified_dn")
    with pytest.raises(runner.WorkflowError, match="verified units"):
        runner.analyze_existing(mosaic, survey_id="s", plot_id="p", output_dir=target, experimental=True)
    assert (target / "manifest.json").read_bytes() == old
    assert not list(tmp_path.glob(".analysis.work-*"))
    failure = tmp_path / "analysis.failure.json"
    assert load_json(failure)["phase"] == "analysis"
    with rasterio.open(mosaic, "r+") as image:
        image.update_tags(units="relative_signal")
    runner.analyze_existing(mosaic, survey_id="s", plot_id="p", output_dir=target, experimental=True)
    assert not failure.exists()


def test_existing_synthetic_mosaic_keeps_synthetic_provenance(tmp_path):
    mosaic = tmp_path / "synthetic.tif"
    create_demo_mosaic(mosaic)
    target = tmp_path / "analysis"
    report = runner.analyze_existing(mosaic, survey_id="s", plot_id="p",
                                     output_dir=target, experimental=True)
    assert report["analysis_eligibility"]["synthetic"] is True
    assert load_json(target / "manifest.json")["analysis_eligibility"]["synthetic"] is True


def test_demo_failure_reports_and_keeps_prior_result(tmp_path, monkeypatch):
    target = tmp_path / "demo"
    runner.run_demo(output_dir=target)
    before = (target / "manifest.json").read_bytes()
    def fail(*args, **kwargs):
        raise ValueError("GIS analysis failed for diagnosis")
    monkeypatch.setattr(runner, "_analyze", fail)
    with pytest.raises(runner.WorkflowError, match="GIS analysis failed"):
        runner.run_demo(output_dir=target)
    failure = load_json(tmp_path / "demo.failure.json")
    assert failure["phase"] == "demo"
    assert (target / "manifest.json").read_bytes() == before
    assert not list(tmp_path.glob(".demo.work-*"))


FOREIGN_FAILURE_CONTENT = [
    pytest.param(b"[]\n", id="json-array"),
    pytest.param(b"null\n", id="json-null"),
    pytest.param(b'"user-owned note"\n', id="json-string"),
    pytest.param(b'{"tool":"another-tool","status":"user data"}\n', id="foreign-object"),
    pytest.param(b"user-owned non-JSON content\n", id="non-json-file"),
]


@pytest.mark.parametrize("foreign_content", FOREIGN_FAILURE_CONTENT)
def test_foreign_failure_file_does_not_break_committed_success(tmp_path, mocked_raw, foreign_content):
    source, _, _ = mocked_raw
    target = tmp_path / "result"
    foreign = tmp_path / "result.failure.json"
    foreign.write_bytes(foreign_content)

    report = runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)

    assert report["status"] == "completed"
    assert load_json(target / "summary.json")["status"] == "completed"
    assert_artifacts(target)
    assert foreign.read_bytes() == foreign_content
    assert not list(tmp_path.glob(".result.work-*"))


@pytest.mark.parametrize("foreign_content", FOREIGN_FAILURE_CONTENT)
def test_foreign_failure_file_keeps_original_failure_and_prior_output(
    tmp_path, mocked_raw, monkeypatch, foreign_content,
):
    source, _, _ = mocked_raw
    target = tmp_path / "result"
    runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)
    prior_manifest = (target / "manifest.json").read_bytes()
    prior_summary = (target / "summary.json").read_bytes()
    foreign = tmp_path / "result.failure.json"
    foreign.write_bytes(foreign_content)

    def fail(*args, **kwargs):
        raise ODMError("PRIMARY_FAILURE: overlapping camera observations missing", code="quality_gate")
    monkeypatch.setattr(runner, "run_odm", fail)

    with pytest.raises(runner.WorkflowError, match="PRIMARY_FAILURE") as error:
        runner.run_pipeline(survey_dir=source, output_dir=target, experimental=True)

    assert isinstance(error.value.__cause__, ODMError)
    assert error.value.__cause__.code == "quality_gate"
    assert foreign.read_bytes() == foreign_content
    assert (target / "manifest.json").read_bytes() == prior_manifest
    assert (target / "summary.json").read_bytes() == prior_summary
    assert not list(tmp_path.glob(".result.work-*"))
