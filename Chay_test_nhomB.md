# HƯỚNG DẪN CHẠY TEST CÁC CHỨC NĂNG ĐÃ LÀM CỦA NHÓM B (`processing/`)

Tài liệu này tổng hợp đầy đủ cách chạy kiểm tra toàn bộ các chức năng Nhóm B đã hoàn thành tính đến hiện tại (**Công việc 1, 2, 3, 4** trong `src/agriscan/` và bộ công cụ nguyên mẫu Tuần 1 trong `src/processing/`).

---

## Bước 0: Mở Terminal và kích hoạt môi trường ảo (`.venv`)

Mở **PowerShell**, di chuyển vào thư mục `processing` và kích hoạt `.venv`:

```powershell
cd d:\University\HK126\HKDN\HKDN_UAV-giam-sat-cay-trong\processing

.\.venv\Scripts\Activate.ps1
```

---

## 1. Test Môi trường & Cấu hình YAML (Công việc 1)

### 1.1. Kiểm tra cài đặt các thư viện xử lý ảnh & GIS (`check_environment.py`)
```powershell
python check_environment.py
```
- **Kết quả kỳ vọng**: In ra phiên bản của `NumPy`, `OpenCV`, `Pandas`, `Rasterio`, `GeoPandas`, `Shapely`, `PyProj` và dòng `AgriScan environment is ready!`.

### 1.2. Kiểm tra nạp toàn bộ 5 file cấu hình YAML (`configs/*.yaml`)
```powershell
python -c "from agriscan.pipeline.steps import load_all_configs; cfg = load_all_configs('configs'); print('Loaded keys:', list(cfg.keys())); print('Camera:', cfg['camera']['model'], cfg['camera']['filter'], 'Bands:', list(cfg['bands'].keys()))"
```
- **Kết quả kỳ vọng**:
  - `Loaded keys: ['project', 'paths', 'processing', 'camera', 'bands', 'metadata', 'calibration', 'indices', 'anomaly']`
  - `Camera: Survey3W RGN Bands: ['red', 'green', 'nir']`

---

## 2. Test Đọc Metadata & Kiểm tra tính hợp lệ thư mục khảo sát (Công việc 2)

Hiện tại trong `..\assets` có 4 thư mục khảo sát:
- `survey_2026-11-02`: Đã có `metadata.json` và 46 file trong `raw/` (22 file `.RAW` + 24 file `.JPG`).
- `survey_2026-11-24`, `survey_2026-11-25`, `survey_2026-11-26`: Mới có thư mục `raw/`, chưa có `metadata.json`.

### 2.1. Test thư mục khảo sát có `metadata.json` (`survey_2026-11-02`)
```powershell
python -m agriscan.cli validate ..\assets\survey_2026-11-02
```
- **Kết quả kỳ vọng**:
  - `"is_valid": true`, `"status": "needs_review"`, `"errors": []`.
  - Đếm đúng `"total_files_in_raw_dir": 46`, `"raw_count": 22`, `"jpg_count": 24`.
  - Kiểm tra toàn bộ 22 file `.RAW` không có file nào hỏng (`"corrupted_files": []`) hay trùng lặp SHA-256 (`"duplicate_files": []`).
  - Quét EXIF của 24 file `.JPG` phát hiện 20 ảnh có tag `Survey3W_RGN` kèm tọa độ GPS (`4000x3000`) và 4 ảnh `1920x1080`.
  - Cảnh báo chính xác trong `"warnings"` về việc thiếu file tấm chuẩn `calibration/target_before.RAW`, `calibration/after_target.RAW` và số lượng RAW/JPG lệch nhau.

### 2.2. Test phát hiện lỗi khi thư mục khảo sát thiếu `metadata.json` (`survey_2026-11-24`)
```powershell
python -m agriscan.cli validate ..\assets\survey_2026-11-24
```
- **Kết quả kỳ vọng**:
  - `"is_valid": false`, `"status": "failed"`.
  - Trong `"errors"` ghi rõ: `"Missing required metadata file: ...\\assets\\survey_2026-11-24\\metadata.json"`, đồng thời vẫn quét kiểm tra được 3 cặp file `.RAW`/`.JPG` trong `raw/`.

---

## 3. Test Giải mã file `.RAW` 12-bit thực tế của MAPIR Survey3W (Công việc 3)

### 3.1. Giải mã file `.RAW` kèm `metadata.json` (từ đợt khảo sát `survey_2026-11-02`)
```powershell
python -m agriscan.cli read-raw ..\assets\survey_2026-11-02\raw\2026_1102_041147_001.RAW --metadata ..\assets\survey_2026-11-02\metadata.json
```
- **Kết quả kỳ vọng**:
  - Giải nén file nhị phân 12-bit packed (`18,000,000 bytes`) bằng `"decoder": "mapir_raw12_le"` thành mảng `4000 × 3000` (`total_pixels: 12000000`, `dtype: "uint16"`).
  - Thống kê điểm ảnh: `"min": 13`, `"max": 2358`, `"mean": 125.89`, `"std": 58.67`, `"zero_pixels": 0`, `"saturated_pixels": 0`.
  - Thông tin camera: `"model": "MAPIR Survey3W"`, `"filter": "RGN"`, `"bands": {"red": 660, "green": 550, "nir": 850}`, `"band_confirmation_status": "confirmed"`.

### 3.2. Giải mã file `.RAW` độc lập không truyền `--metadata` (từ đợt khảo sát `survey_2026-11-26`)
```powershell
python -m agriscan.cli read-raw ..\assets\survey_2026-11-26\raw\2026_1126_132937_001.RAW
```
- **Kết quả kỳ vọng**: Giải mã thành công mảng `4000 × 3000` và sử dụng cấu hình camera mặc định (`"band_confirmation_status": "default_camera_config"`).

---

## 4. Test Tách 3 kênh phổ RGN sang file `.tif` (Công việc 4)

### 4.1. Chế độ mặc định — Giữ độ phân giải gốc của mặt phẳng Bayer (`1500 × 2000`)
```powershell
python -m agriscan.cli extract-bands ..\assets\survey_2026-11-02\raw\2026_1102_041147_001.RAW --metadata ..\assets\survey_2026-11-02\metadata.json --output data/intermediate/2026_1102_041147_001
```
- **Kết quả kỳ vọng**:
  - Tạo thư mục `processing/data/intermediate/2026_1102_041147_001/` gồm 4 file: `red.tif`, `green.tif`, `nir.tif` và `band_metadata.json`.
  - Mỗi kênh có `"shape": [1500, 2000]`, `"dtype": "float32"`:
    - `red` (660 nm, vị trí Bayer `R`): `min=15.0, max=1610.0, mean=122.59`
    - `green` (550 nm, trung bình `G1+G2_avg`): `min=19.5, max=2112.5, mean=132.8`
    - `nir` (850 nm, vị trí Bayer `B`): `min=13.0, max=577.0, mean=115.35`

### 4.2. Chế độ nội suy đầy đủ độ phân giải cảm biến (`3000 × 4000`) với cờ `--full-res`
```powershell
python -m agriscan.cli extract-bands ..\assets\survey_2026-11-02\raw\2026_1102_041147_001.RAW --metadata ..\assets\survey_2026-11-02\metadata.json --output data/intermediate/2026_1102_041147_001_full --full-res
```
- **Kết quả kỳ vọng**: `"keep_half_resolution": false`, cả 3 file `red.tif`, `green.tif`, `nir.tif` đều có `"shape": [3000, 4000]`.

### 4.3. Kiểm tra metadata tag bên trong các file `.tif` bằng `rasterio`
```powershell
python -c "import rasterio; [print(b, rasterio.open(f'data/intermediate/2026_1102_041147_001/{b}.tif').shape, rasterio.open(f'data/intermediate/2026_1102_041147_001/{b}.tif').tags()) for b in ('red', 'green', 'nir')]"
```
- **Kết quả kỳ vọng**:
  - `red (1500, 2000) {'band_name': 'red', 'bayer_position': 'R', 'camera_filter': 'RGN', 'wavelength_nm': '660'}`
  - `green (1500, 2000) {'band_name': 'green', 'bayer_position': 'G1+G2_avg', 'camera_filter': 'RGN', 'wavelength_nm': '550'}`
  - `nir (1500, 2000) {'band_name': 'nir', 'bayer_position': 'B', 'camera_filter': 'RGN', 'wavelength_nm': '850'}`

---

## 5. Test Chạy Luồng Tổng hợp Công việc 1 → 4 (`agriscan.cli run`)

```powershell
python -m agriscan.cli run --config configs/default.yaml --input ..\assets\survey_2026-11-02
```
- **Kết quả kỳ vọng**:
  ```text
  =============================================
  AGRISCAN PROCESSING
  =============================================
  Project: AgriScan
  Version: 1.0.0
  Input: ..\assets\survey_2026-11-02
  Output: data/output
  Configuration loaded successfully!
  Validation status: needs_review (RAW=22, JPG=24)
  Sample RAW decoded: 2026_1102_041147_001.RAW -> shape=(3000, 4000), dtype=uint16, min=13, max=2358
  Extracted bands saved to data\intermediate\2026_1102_041147_001: red(660nm), green(550nm), nir(850nm)
  ```

---

## 6. Test Bộ công cụ nguyên mẫu Tuần 1 (`src/processing/`)

### 6.1. Sinh dữ liệu Bayer mosaic giả lập 12-bit (`make-synthetic-survey`)
```powershell
make-synthetic-survey --output data/synthetic --size 512
```
- **Kết quả kỳ vọng**: Sinh ra `data/synthetic/mosaic.npy` và `data/synthetic/flat.npy` kích thước `512 × 512`.

### 6.2. Tách 4 mặt phẳng Bayer (`R, G1, G2, B`) và xuất ảnh `.png` xem nhanh (`process-survey`)
- **Chạy trên dữ liệu giả lập**:
  ```powershell
  process-survey data/synthetic/mosaic.npy --output output/synthetic-001 --pattern RGGB
  ```
- **Chạy trên file `.RAW` thực tế của MAPIR Survey3W**:
  ```powershell
  process-survey ..\assets\survey_2026-11-02\raw\2026_1102_041147_001.RAW --output output/real-raw-001
  ```
- **Kết quả kỳ vọng**: Tạo 4 file `.npy` (`R.npy`, `G1.npy`, `G2.npy`, `B.npy`), 4 file ảnh 16-bit `.png` để mở xem bằng mắt thường và file `metadata.json`.

### 6.3. Kiểm tra toán học hàm khử tối góc (`correct_vignetting`)
```powershell
python -c "import numpy as np; from processing.vignetting import radial_flat, correct_vignetting; flat = radial_flat((100, 100), 0.35); img = np.full((100, 100), 1000.0, dtype=np.float32) * flat; restored = correct_vignetting(img, flat); print('Std truoc khi khu:', round(float(img.std()), 4), '-> Sau khi khu:', round(float(restored.std()), 6))"
```
- **Kết quả kỳ vọng**: `Std truoc khi khu: 115.2667 -> Sau khi khu: 2.9e-05` (độ lệch chuẩn giảm từ `115.27` về `0.000029` — tức sai số chỉ `~0.000003%` do làm tròn dấu phẩy động 32-bit `float32`, khôi phục hoàn toàn độ đồng đều sáng từ tâm ra góc ảnh).
