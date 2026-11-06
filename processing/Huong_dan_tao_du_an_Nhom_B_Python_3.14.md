# Hướng dẫn tạo dự án Nhóm B – AgriScan (Python 3.14)

> Tài liệu hướng dẫn khởi tạo dự án xử lý ảnh đa phổ cho Nhóm B. Dự án tiếp nhận dữ liệu từ Nhóm A, xử lý ảnh MAPIR Survey3, tính chỉ số thực vật, phát hiện khu vực bất thường và bàn giao kết quả cho Nhóm C.

## 1. Tổng quan dự án

**Tên dự án:** `agriscan-processing`

### Nhiệm vụ của Nhóm B

1. Tiếp nhận ảnh RAW/JPG và metadata từ Nhóm A.
2. Kiểm tra tính hợp lệ của dữ liệu.
3. Giải mã ảnh RAW MAPIR.
4. Tách các kênh phổ mà camera thực tế hỗ trợ.
5. Hiệu chuẩn ảnh theo quy trình phù hợp với thiết bị.
6. Ghép ảnh thành Orthomosaic nếu dữ liệu đáp ứng điều kiện.
7. Tính chỉ số NDVI.
8. Phân tích và phát hiện khu vực bất thường.
9. Xuất kết quả để Nhóm C tích hợp vào hệ thống.

### Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.14 |
| IDE | Visual Studio Code |
| Xử lý ảnh | OpenCV, NumPy |
| Xử lý raster | Rasterio, GDAL nếu cần |
| Dữ liệu không gian | GeoPandas, Shapely, PyProj |
| Thống kê | Pandas, NumPy |
| Biểu đồ | Matplotlib |
| Cấu hình | PyYAML |
| CLI | Typer |
| Kiểm thử | Pytest |
| Quản lý mã nguồn | Git, GitHub |

**Lưu ý:** Tài liệu này giả định các thư viện cần thiết đã được cài đặt và kiểm tra thành công trên Python 3.14. Mỗi thành viên vẫn cần cài chúng vào môi trường ảo riêng của dự án.

---

## 2. Tạo thư mục dự án

Tạo cấu trúc ban đầu:

```text
AgriScan/
└── agriscan-processing/
```

Mở thư mục `agriscan-processing` bằng VS Code: **File → Open Folder**.

Có thể tạo nhanh bằng PowerShell:

```powershell
mkdir AgriScan
cd AgriScan
mkdir agriscan-processing
cd agriscan-processing
code .
```

---

## 3. Tạo môi trường ảo Python 3.14

Kiểm tra Python:

```powershell
py -3.14 --version
```

Kết quả mong đợi:

```text
Python 3.14.x
```

Tạo môi trường ảo:

```powershell
py -3.14 -m venv .venv
```

Kích hoạt trên PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Nếu dùng Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

Sau khi kích hoạt, Terminal sẽ có tiền tố `(.venv)`.

Nâng cấp pip:

```powershell
python -m pip install --upgrade pip
```

Kiểm tra Python đang được dùng:

```powershell
python --version
```

Phải hiển thị Python 3.14.x.

### Chọn interpreter trong VS Code

1. Nhấn `Ctrl + Shift + P`.
2. Chọn `Python: Select Interpreter`.
3. Chọn interpreter trong `agriscan-processing\.venv`.

Không nên dùng trực tiếp Python toàn cục để chạy dự án.

---

## 4. Tạo cấu trúc thư mục

Dự án sử dụng mô hình `src-layout`:

```text
agriscan-processing/
│
├── .venv/
│
├── configs/
│   ├── default.yaml
│   ├── camera.yaml
│   ├── calibration.yaml
│   ├── indices.yaml
│   └── anomaly.yaml
│
├── data/
│   ├── input/
│   ├── calibration/
│   ├── intermediate/
│   └── output/
│
├── src/
│   └── agriscan/
│       ├── __init__.py
│       │
│       ├── io/
│       │   ├── __init__.py
│       │   ├── raw_reader.py
│       │   ├── metadata_reader.py
│       │   ├── image_validator.py
│       │   └── raster_io.py
│       │
│       ├── calibration/
│       │   ├── __init__.py
│       │   ├── decoder.py
│       │   ├── band_extractor.py
│       │   ├── vignetting.py
│       │   ├── reflectance.py
│       │   └── quality_check.py
│       │
│       ├── mosaicking/
│       │   ├── __init__.py
│       │   ├── georeference.py
│       │   ├── mosaic_builder.py
│       │   └── mosaic_quality.py
│       │
│       ├── indices/
│       │   ├── __init__.py
│       │   ├── ndvi.py
│       │   ├── gndvi.py
│       │   ├── savi.py
│       │   ├── masking.py
│       │   └── statistics.py
│       │
│       ├── anomalies/
│       │   ├── __init__.py
│       │   ├── absolute.py
│       │   ├── spatial.py
│       │   ├── temporal.py
│       │   ├── clustering.py
│       │   └── ranking.py
│       │
│       ├── export/
│       │   ├── __init__.py
│       │   ├── geotiff_export.py
│       │   ├── geojson_export.py
│       │   ├── csv_export.py
│       │   └── report_export.py
│       │
│       └── pipeline/
│           ├── __init__.py
│           ├── runner.py
│           └── steps.py
│
├── tests/
│   ├── test_environment.py
│   ├── test_ndvi.py
│   ├── test_statistics.py
│   ├── test_calibration.py
│   └── test_anomalies.py
│
├── scripts/
│   └── check_environment.py
│
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── requirements-lock.txt
└── README.md
```

### Tạo thư mục bằng PowerShell

Chạy tại thư mục gốc `agriscan-processing`:

```powershell
$dirs = @(
    "configs",
    "data/input",
    "data/calibration",
    "data/intermediate",
    "data/output",
    "src/agriscan/io",
    "src/agriscan/calibration",
    "src/agriscan/mosaicking",
    "src/agriscan/indices",
    "src/agriscan/anomalies",
    "src/agriscan/export",
    "src/agriscan/pipeline",
    "tests",
    "scripts"
)

foreach ($dir in $dirs) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}
```

Tạo các file `__init__.py`:

```powershell
$packages = @(
    "src/agriscan",
    "src/agriscan/io",
    "src/agriscan/calibration",
    "src/agriscan/mosaicking",
    "src/agriscan/indices",
    "src/agriscan/anomalies",
    "src/agriscan/export",
    "src/agriscan/pipeline"
)

foreach ($package in $packages) {
    New-Item -ItemType File -Force -Path "$package/__init__.py" | Out-Null
}
```

Tạo file giữ các thư mục dữ liệu trong Git:

```powershell
New-Item -ItemType File -Force -Path "data/input/.gitkeep"
New-Item -ItemType File -Force -Path "data/calibration/.gitkeep"
New-Item -ItemType File -Force -Path "data/intermediate/.gitkeep"
New-Item -ItemType File -Force -Path "data/output/.gitkeep"
```

---

## 5. Tạo file `requirements.txt`

Tạo file `requirements.txt` ở thư mục gốc:

```txt
numpy
opencv-python
pandas
matplotlib
PyYAML
typer
pytest
ruff
rasterio
geopandas
shapely
pyproj
```

Cài thư viện trong môi trường ảo:

```powershell
pip install -r requirements.txt
```

Kiểm tra:

```powershell
pip list
```

### Khóa phiên bản thư viện

Sau khi cài đặt và kiểm thử thành công:

```powershell
pip freeze > requirements-lock.txt
```

- `requirements.txt`: danh sách thư viện trực tiếp dự án cần.
- `requirements-lock.txt`: phiên bản cụ thể đã được cài và kiểm thử.

Các thành viên khác có thể đồng bộ môi trường bằng:

```powershell
pip install -r requirements-lock.txt
```

Chỉ cập nhật file khóa phiên bản sau khi đã kiểm tra tương thích trên Python 3.14 và Windows của nhóm.

---

## 6. Tạo file `pyproject.toml`

Tạo `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[project]
name = "agriscan-processing"
version = "1.0.0"
description = "Multispectral image processing and anomaly screening for AgriScan"
requires-python = ">=3.14"
dependencies = [
    "numpy",
    "opencv-python",
    "pandas",
    "matplotlib",
    "PyYAML",
    "typer",
    "rasterio",
    "geopandas",
    "shapely",
    "pyproj"
]

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff"
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Cài dự án ở chế độ editable:

```powershell
pip install -e ".[dev]"
```

Sau đó có thể import module theo package:

```python
from agriscan.indices.ndvi import calculate_ndvi
```

Khi sửa code trong `src/agriscan`, không cần cài lại package.

---

## 7. Tạo các file cấu hình YAML

Các tham số xử lý nên được tách khỏi code để dễ thay đổi, kiểm thử và quản lý theo từng loại camera.

### 7.1. `configs/default.yaml`

```yaml
project:
  name: AgriScan
  version: 1.0.0

paths:
  input: data/input
  calibration: data/calibration
  intermediate: data/intermediate
  output: data/output

processing:
  save_intermediate: true
  overwrite_output: false
  continue_on_error: false
```

### 7.2. `configs/camera.yaml`

```yaml
camera:
  manufacturer: MAPIR
  model: Survey3
  filter: null

bands:
  red:
    enabled: true
    wavelength_nm: null

  nir:
    enabled: true
    wavelength_nm: null

  green:
    enabled: false
    wavelength_nm: null

metadata:
  require_camera_model: true
  require_filter: true
```

Các giá trị `filter` và `wavelength_nm` phải được cập nhật theo đúng camera và bộ lọc thực tế. Không mặc định mọi phiên bản Survey3 đều có cùng các kênh phổ.

### 7.3. `configs/calibration.yaml`

```yaml
calibration:
  enabled: true

  reflectance:
    method: null
    target_type: null

  vignetting:
    enabled: false

  quality_check:
    enabled: true
```

Để `method` và `target_type` là `null` cho đến khi nhóm xác minh quy trình hiệu chuẩn phù hợp với thiết bị và bảng chuẩn.

### 7.4. `configs/indices.yaml`

```yaml
indices:
  ndvi:
    enabled: true

  gndvi:
    enabled: false

  savi:
    enabled: false
    soil_factor: 0.5
```

### 7.5. `configs/anomaly.yaml`

```yaml
anomaly:
  methods:
    absolute: true
    spatial: true
    temporal: false

  thresholds:
    ndvi_min: null
    spatial_z_score: null

  severity:
    low: 1
    medium: 2
    high: 3
```

Ngưỡng phát hiện bất thường cần được xác định bằng dữ liệu khảo sát và đánh giá thực nghiệm, không sử dụng các giá trị minh họa như ngưỡng chính thức.

---

## 8. Xây dựng module đọc cấu hình

### 8.1. File `src/agriscan/pipeline/steps.py`

```python
from pathlib import Path

import yaml


def load_config(config_path: str) -> dict:
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Không tìm thấy file cấu hình: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("Nội dung cấu hình không hợp lệ")

    return config
```

### 8.2. File `src/agriscan/pipeline/runner.py`

```python
from agriscan.pipeline.steps import load_config


def run_pipeline(config_path: str):
    config = load_config(config_path)

    print("=" * 45)
    print("AGRISCAN PROCESSING")
    print("=" * 45)

    print("Project:", config["project"]["name"])
    print("Version:", config["project"]["version"])

    print("Input:", config["paths"]["input"])
    print("Output:", config["paths"]["output"])

    print("Configuration loaded successfully!")
```

### 8.3. File `scripts/check_environment.py`

```python
import sys

import cv2
import geopandas
import matplotlib
import numpy
import pandas
import rasterio
import shapely
import pyproj
import yaml

from agriscan.pipeline.runner import run_pipeline


def main():
    print("Python:", sys.version)
    print("NumPy:", numpy.__version__)
    print("OpenCV:", cv2.__version__)
    print("Pandas:", pandas.__version__)
    print("Rasterio:", rasterio.__version__)
    print("GeoPandas:", geopandas.__version__)
    print("Shapely:", shapely.__version__)
    print("PyProj:", pyproj.__version__)
    print("Matplotlib:", matplotlib.__version__)
    print("PyYAML:", yaml.__version__)

    print("\nChecking configuration...")
    run_pipeline("configs/default.yaml")


if __name__ == "__main__":
    main()
```

Chạy chương trình:

```powershell
python scripts/check_environment.py
```

Nếu chương trình in thông tin thư viện và `Configuration loaded successfully!`, phần khởi tạo đã hoạt động.

---

## 9. Xây dựng chức năng tính NDVI đầu tiên

Đây là module nên triển khai sớm để kiểm tra công thức tính chỉ số thực vật trước khi tích hợp với ảnh thực tế.

### 9.1. File `src/agriscan/indices/ndvi.py`

```python
import numpy as np


def calculate_ndvi(red, nir):
    """
    Tính NDVI từ hai mảng dữ liệu Red và NIR.

    Parameters:
        red: Mảng dữ liệu kênh Red.
        nir: Mảng dữ liệu kênh NIR.

    Returns:
        Mảng NDVI kiểu float32.
    """

    red = np.asarray(red, dtype=np.float32)
    nir = np.asarray(nir, dtype=np.float32)

    if red.shape != nir.shape:
        raise ValueError(
            "Kích thước ảnh Red và NIR không giống nhau"
        )

    denominator = nir + red

    ndvi = np.full(
        red.shape,
        np.nan,
        dtype=np.float32
    )

    valid = (
        np.isfinite(red)
        & np.isfinite(nir)
        & (denominator != 0)
    )

    ndvi[valid] = (
        (nir[valid] - red[valid])
        / denominator[valid]
    )

    return ndvi
```

### 9.2. File `tests/test_ndvi.py`

```python
import numpy as np
import pytest

from agriscan.indices.ndvi import calculate_ndvi


def test_calculate_ndvi():
    red = np.array(
        [[0.2, 0.3]],
        dtype=np.float32
    )

    nir = np.array(
        [[0.8, 0.7]],
        dtype=np.float32
    )

    result = calculate_ndvi(red, nir)

    expected = np.array(
        [[0.6, 0.4]],
        dtype=np.float32
    )

    np.testing.assert_allclose(
        result,
        expected,
        atol=1e-6
    )


def test_zero_denominator():
    red = np.array([[0.0]])
    nir = np.array([[0.0]])

    result = calculate_ndvi(red, nir)

    assert np.isnan(result[0, 0])


def test_different_shapes():
    red = np.array([[0.2, 0.3]])
    nir = np.array([[0.8]])

    with pytest.raises(ValueError):
        calculate_ndvi(red, nir)
```

Chạy kiểm thử:

```powershell
pytest -v
```

Kết quả mong đợi:

```text
test_calculate_ndvi PASSED
test_zero_denominator PASSED
test_different_shapes PASSED
```

Đây mới là kiểm thử công thức trên dữ liệu số. Khi xử lý ảnh thực tế, cần bảo đảm Red và NIR được căn chỉnh, có cùng hệ số tỷ lệ và cùng phương pháp hiệu chuẩn.

---

## 10. Tạo file `.gitignore`

Tạo file `.gitignore` tại thư mục gốc:

```gitignore
# Python cache
__pycache__/
*.py[cod]
*.egg-info/

# Virtual environment
.venv/
venv/

# IDE
.vscode/
.idea/

# Environment
.env

# Testing
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/

# Data
data/input/*
data/calibration/*
data/intermediate/*
data/output/*

# Keep folder placeholders
!data/input/.gitkeep
!data/calibration/.gitkeep
!data/intermediate/.gitkeep
!data/output/.gitkeep

# Logs
*.log

# OS
.DS_Store
Thumbs.db
```

Không đưa ảnh RAW, JPG, GeoTIFF dung lượng lớn lên GitHub. Dữ liệu nên được quản lý riêng bằng ổ cứng chung hoặc kho lưu trữ của nhóm.

---

## 11. Quy định dữ liệu đầu vào và đầu ra

Nhóm B phải thống nhất định dạng bàn giao với Nhóm A và Nhóm C ngay từ đầu.

### 11.1. Dữ liệu nhận từ Nhóm A

Ví dụ một lần khảo sát:

```text
survey_20261106_001/
│
├── metadata.json
│
├── raw/
│   ├── IMG_001.RAW
│   ├── IMG_002.RAW
│   └── IMG_003.RAW
│
├── jpg/
│   ├── IMG_001.JPG
│   ├── IMG_002.JPG
│   └── IMG_003.JPG
│
├── calibration/
│   └── calibration_images/
│
├── gcp/
│   └── gcp.csv
│
└── logs/
    └── survey-log.xlsx
```

Nhóm B cần nhận tối thiểu:

- Ảnh RAW gốc.
- Metadata của lần khảo sát.
- Thông tin camera và bộ lọc.
- Ảnh hiệu chuẩn nếu quy trình yêu cầu.
- Ảnh JPG để xem trước và đối chiếu.
- Thông tin tọa độ/GCP nếu có.

### 11.2. Kết quả Nhóm B xuất ra

```text
survey_20261106_001/
│
├── reflectance/
│   ├── red.tif
│   └── nir.tif
│
├── mosaic/
│   └── orthomosaic.tif
│
├── indices/
│   └── ndvi.tif
│
├── masks/
│   └── vegetation_mask.tif
│
├── statistics/
│   └── statistics.csv
│
├── anomalies/
│   └── alerts.geojson
│
└── reports/
    └── processing_report.json
```

Không phải lần khảo sát nào cũng tạo được tất cả các tệp trên. Chỉ xuất dữ liệu có tọa độ khi có cơ sở định vị phù hợp; chỉ coi dữ liệu là phản xạ đã hiệu chuẩn khi quy trình hiệu chuẩn được xác minh.

---

## 12. Thứ tự triển khai các module

| Giai đoạn | Module | Công việc |
|---|---|---|
| 1 | `io/` | Đọc metadata, kiểm tra ảnh và dữ liệu |
| 2 | `calibration/decoder.py` | Giải mã RAW MAPIR |
| 3 | `calibration/band_extractor.py` | Xác định và tách kênh phổ |
| 4 | `calibration/` | Hiệu chuẩn và kiểm tra chất lượng |
| 5 | `mosaicking/` | Ghép ảnh, kiểm tra tọa độ |
| 6 | `indices/` | Tính NDVI, tạo mask, thống kê |
| 7 | `anomalies/` | Phân tích không gian và thời gian |
| 8 | `export/` | Xuất GeoTIFF, GeoJSON, CSV, JSON |
| 9 | `pipeline/` | Kết nối toàn bộ quy trình |

### Lưu ý về MAPIR Survey3

Không mặc định mọi ảnh RAW MAPIR đều đọc được bằng `rawpy`. Trước tiên cần kiểm tra định dạng file thực tế, phần mềm giải mã được MAPIR hỗ trợ, thứ tự kênh và thông tin bộ lọc. Chỉ sau khi xác minh mới triển khai `decoder.py` và `band_extractor.py`.

---

## 13. Phân công công việc cho hai thành viên

| Thành viên | Phụ trách | Module |
|---|---|---|
| Thành viên 1 | Xử lý ảnh | `io/`, `calibration/`, `mosaicking/` |
| Thành viên 2 | Phân tích dữ liệu | `indices/`, `anomalies/`, `export/` |
| Cả hai | Tích hợp | `pipeline/`, `tests/`, tài liệu |

Hai thành viên cần thống nhất trước các thông tin:

- Kiểu dữ liệu ảnh.
- Thứ tự kênh phổ.
- CRS và hệ tọa độ.
- Giá trị NoData.
- Đơn vị và thang đo phản xạ.
- Mã khảo sát.
- Mã đơn vị phân tích.

---

## 14. Kế hoạch triển khai tham khảo

| Thời gian | Công việc | Kết quả |
|---|---|---|
| Tuần 1 | Khởi tạo dự án, nhận dữ liệu mẫu | Chạy được môi trường Python 3.14 |
| Tuần 2 | Đọc RAW, metadata, xác minh kênh phổ | Đọc và kiểm tra được ảnh thực tế |
| Tuần 3 | Hiệu chuẩn và kiểm tra chất lượng | Có dữ liệu ảnh sau hiệu chuẩn |
| Tuần 4 | Ghép ảnh, xử lý tọa độ | Có Orthomosaic nếu đủ điều kiện |
| Tuần 5 | Tính NDVI và thống kê | Có bản đồ NDVI |
| Tuần 6 | Phân tích bất thường | Có danh sách vùng cần kiểm tra |
| Tuần 7 | Xuất kết quả và tích hợp Nhóm C | Có GeoTIFF, GeoJSON, CSV, JSON |
| Tuần 8 trở đi | Kiểm thử và cải thiện | Báo cáo đánh giá chất lượng |

Thời gian thực tế phụ thuộc vào việc nhận dữ liệu MAPIR, xác minh quy trình hiệu chuẩn và khả năng ghép ảnh.

---

## 15. Checklist khởi tạo dự án

- [ ] Tạo thư mục `agriscan-processing`.
- [ ] Tạo môi trường ảo Python 3.14.
- [ ] Chọn đúng interpreter `.venv` trong VS Code.
- [ ] Tạo cấu trúc thư mục `src/agriscan`.
- [ ] Tạo `requirements.txt` và `pyproject.toml`.
- [ ] Cài package bằng `pip install -e ".[dev]"`.
- [ ] Tạo 5 file cấu hình YAML.
- [ ] Tạo module đọc cấu hình.
- [ ] Tạo module tính NDVI.
- [ ] Chạy `pytest` thành công.
- [ ] Đưa dự án lên GitHub.
- [ ] Nhận một bộ ảnh MAPIR thực tế từ Nhóm A.

## 16. Mốc quan trọng nhất

Sau khi tạo xong cấu trúc dự án, hãy ưu tiên lấy một bộ ảnh RAW thực tế từ Nhóm A và xác minh khả năng giải mã MAPIR.

Không nên phát triển sâu thuật toán NDVI và phát hiện bất thường trên dữ liệu giả lập rồi mới phát hiện cách giải mã hoặc thứ tự kênh của camera không đúng.

**Tiêu chí hoàn thành giai đoạn khởi tạo:** dự án chạy trên Python 3.14 trong `.venv`, import được các thư viện, đọc được cấu hình YAML, chạy được test NDVI và có cấu trúc module thống nhất để hai thành viên cùng phát triển.
