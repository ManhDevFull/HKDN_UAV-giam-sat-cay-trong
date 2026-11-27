"""Configuration mistakes fail before expensive image processing starts."""

from importlib.resources import files
from pathlib import Path

import pytest
import yaml

from agriscan.pipeline.workflow_config import load_workflow_config


def test_editable_configuration_matches_packaged_defaults():
    editable = Path(__file__).parents[1] / "configs" / "workflow.yaml"
    packaged = files("agriscan").joinpath("configs/workflow.yaml")
    assert yaml.safe_load(editable.read_text(encoding="utf-8")) == yaml.safe_load(packaged.read_text(encoding="utf-8"))
    assert load_workflow_config(editable) == load_workflow_config()
    # Both radiometric profiles are resources required after a normal pip install.
    assert files("processing").joinpath("profiles/default.json").is_file()
    assert files("processing").joinpath("profiles/survey3w.json").is_file()


def test_packaged_defaults_work_outside_repository_and_merge_overrides(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    defaults = load_workflow_config()
    path = tmp_path / "custom.yaml"
    path.write_text("\ufeffmosaicking:\n  max_concurrency: 2\nanomaly:\n  absolute_threshold: 0.3\n", encoding="utf-8")
    changed = load_workflow_config(path)
    assert changed["mosaicking"]["max_concurrency"] == 2
    assert changed["anomaly"]["absolute_threshold"] == 0.3
    assert changed["mosaicking"]["common_scale"] == defaults["mosaicking"]["common_scale"]
    assert load_workflow_config() == defaults


@pytest.mark.parametrize("override,match", [
    ([], "YAML object"),
    ({"unknown": 1}, "Unknown workflow setting"),
    ({"mosaicking": []}, "mapping"),
    ({"schema_version": True}, "schema_version"),
    ({"camera": {"filter": "OCN"}}, "Survey3W RGN"),
    ({"radiometry": {"mode": "reflectance"}}, "radiometry"),
    ({"radiometry": {"allow_experimental": "false"}}, "radiometry"),
    ({"mosaicking": {"max_concurrency": "4"}}, "finite number"),
    ({"mosaicking": {"max_concurrency": True}}, "finite number"),
    ({"mosaicking": {"max_concurrency": 2.5}}, "integer"),
    ({"mosaicking": {"memory_gb": float("nan")}}, "finite number"),
    ({"mosaicking": {"memory_gb": 1}}, "memory_gb"),
    ({"mosaicking": {"timeout_seconds": 0}}, "timeout_seconds"),
    ({"mosaicking": {"min_images": 2}}, "min_images"),
    ({"mosaicking": {"common_scale": 65536}}, "common_scale"),
    ({"mosaicking": {"max_retries": 0.5}}, "integer"),
    ({"mosaicking": {"max_retries": 3}}, "max_retries"),
    ({"mosaicking": {"min_used_ratio": 1.1}}, "min_used_ratio"),
    ({"mosaicking": {"min_used_ratio": 0.8}}, "min_used_ratio"),
    ({"mosaicking": {"orthophoto_resolution": 0}}, "orthophoto_resolution"),
    ({"mosaicking": {"feature_quality": "best"}}, "feature_quality"),
    ({"mosaicking": {"image": "opendronemap/odm:latest"}}, "versioned official"),
    ({"mosaicking": {"image": "untrusted/odm:3.5.6"}}, "versioned official"),
    ({"indices": {"red_band": 3}}, "different"),
    ({"indices": {"nir_band": 1.5}}, "integer"),
    ({"indices": {"vegetation_threshold": True}}, "finite number"),
    ({"indices": {"vegetation_threshold": 2}}, "vegetation_threshold"),
    ({"indices": {"brightness_min": -1}}, "brightness_min"),
    ({"indices": {"reflectance_scale": 0}}, "reflectance_scale"),
    ({"grid": {"cell_size_m": 0}}, "cell_size_m"),
    ({"grid": {"max_cells": 1.5}}, "integer"),
    ({"anomaly": {"spatial_z_threshold": 0}}, "negative"),
    ({"anomaly": {"min_valid_pixels": 0}}, "min_valid_pixels"),
    ({"anomaly": {"min_vegetation_fraction": -0.1}}, "min_vegetation_fraction"),
    ({"anomaly": {"min_coverage_fraction": 1.1}}, "min_coverage_fraction"),
    ({"anomaly": {"min_spatial_units": 2}}, "min_spatial_units"),
    ({"anomaly": {"merge_adjacent": "false"}}, "true or false"),
    ({"anomaly": {"ranking": {"severity_weight": -1}}}, "nonnegative"),
    ({"anomaly": {"ranking": {"severity_weight": 0, "area_weight": 0, "agreement_weight": 0}}}, "positive"),
])
def test_rejects_malformed_configuration_before_processing(tmp_path, override, match):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(override), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_workflow_config(path)


def test_malformed_yaml_has_actionable_value_error(tmp_path):
    from agriscan.pipeline.workflow_config import load_workflow_config
    path = tmp_path / 'broken.yaml'
    path.write_text('grid: [unterminated')
    with pytest.raises(ValueError, match='Invalid workflow YAML'):
        load_workflow_config(path)
