"""Pipeline configuration loading and step helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

CONFIG_FILES = (
    "default.yaml",
    "camera.yaml",
    "calibration.yaml",
    "indices.yaml",
    "anomaly.yaml",
)


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load and validate a YAML configuration file."""
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file cấu hình: {path}")

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise TypeError(f"Nội dung cấu hình không hợp lệ trong: {path}")

    return config


def load_all_configs(config_dir: str | Path = "configs") -> dict[str, Any]:
    """Load and merge all 5 standard YAML configuration files from a directory."""
    directory = Path(config_dir)
    if not directory.exists() or not directory.is_dir():
        raise FileNotFoundError(f"Không tìm thấy thư mục cấu hình: {directory}")

    merged: dict[str, Any] = {}
    for filename in CONFIG_FILES:
        file_path = directory / filename
        if file_path.exists():
            merged.update(load_config(file_path))
    return merged
