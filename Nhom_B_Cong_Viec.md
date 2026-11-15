Dưới đây là các phần công việc Nhóm B cần làm tiếp theo theo đúng thứ tự triển khai từ nền tảng đến khi bàn giao cho Nhóm C:

1. **Chuẩn hóa cấu trúc dự án và file cấu hình (`configs/` & `src/agriscan/`)**
   - Tổ chức lại thư mục code thành các module chuẩn: `io/`, `calibration/`, `mosaicking/`, `indices/`, `anomalies/`, `export/`, `pipeline/` và `tests/`.
   - Tạo 5 file cấu hình YAML (`default.yaml`, `camera.yaml`, `calibration.yaml`, `indices.yaml`, `anomaly.yaml`) và hàm đọc cấu hình `load_config()`.

2. **Đọc Metadata và kiểm tra tính hợp lệ dữ liệu đầu vào (`io/metadata_reader.py`, `io/image_validator.py`)**
   - Đọc và kiểm tra cấu trúc [metadata.json](file:///d:/University/HK126/HKDN/HKDN_UAV-giam-sat-cay-trong/assets/metadata.json) (mã survey, plot, camera `MAPIR Survey3W`, filter `RGN`, bước sóng `660/550/850nm`).
   - Tự động kiểm tra thư mục khảo sát: đối chiếu số lượng ảnh, phát hiện cặp `.RAW`/`.JPG` bị lẻ, kiểm tra sự tồn tại của ảnh tấm chuẩn (`target_before`, `target_after`), kiểm tra EXIF/GPS và checksum SHA-256.

3. **Giải mã file `.RAW` thực tế của MAPIR Survey3W (`io/raw_reader.py`, `calibration/decoder.py`)**
   - Viết bộ giải mã đọc định dạng nhị phân **12-bit packed headerless** (`18,000,000 bytes` $\rightarrow$ mảng `3000×4000` pixel `uint16`) cho các file `.RAW` trong `assets/raw/` (hoặc tích hợp quy trình giải mã chuẩn của MAPIR thay vì chỉ gọi `rawpy` mặc định).

4. **Tách kênh phổ theo bộ lọc RGN (`calibration/band_extractor.py`)**
   - Ánh xạ đúng cấu trúc Bayer của cảm biến MAPIR Survey3W RGN để tách thành 3 kênh thực tế: **Red (660nm)**, **Green (550nm)**, **NIR (850nm)** và xuất ảnh trung gian (`.tif`).

5. **Hoàn thiện khử tối góc và hiệu chuẩn phản xạ (`calibration/vignetting.py`, `calibration/reflectance.py`, `calibration/quality_check.py`)**
   - Thay mảng `flat` toàn số 1 hiện tại bằng dữ liệu flat-field thực tế theo từng kênh.
   - Đọc ảnh chụp tấm chuẩn `MAPIR T4P-R25` trước/sau khảo sát để chuyển giá trị pixel (DN) sang độ phản xạ bề mặt (Reflectance).
   - Kiểm tra điểm ảnh bão hòa/NoData và đánh giá sai lệch phản xạ (mục tiêu < 5%).

6. **Đọc/ghi Raster chuẩn GIS và ghép ảnh bình đồ (`io/raster_io.py`, `mosaicking/`)**
   - Viết hàm đọc/ghi GeoTIFF bảo toàn hệ tọa độ (CRS), `transform` và `NoData` bằng `rasterio`.
   - Kiểm tra điều kiện ghép ảnh (overlap, GPS), tích hợp ghép ảnh (OpenDroneMap hoặc quy trình căn chỉnh kênh) để tạo `orthomosaic.tif` và báo cáo `mosaic-quality.json`.

7. **Tính chỉ số thực vật (`indices/ndvi.py`, `gndvi.py`, `savi.py`)**
   - Triển khai công thức tính **NDVI** $=\frac{NIR - Red}{NIR + Red}$ (và GNDVI/SAVI khi cần) trên mảng `float32`, xử lý an toàn pixel `NoData`/`NaN`, mẫu số bằng `0` và kiểm tra khớp kích thước/CRS giữa hai kênh.

8. **Tạo mặt nạ thực vật, chia ô phân tích (Unit) và tính thống kê (`indices/masking.py`, `indices/statistics.py`)**
   - Áp ngưỡng NDVI (thử nghiệm ban đầu `> 0.2`) để lọc bỏ đất trống/vật thể, xuất `vegetation-mask.tif`.
   - Chia khu vực khảo sát thành các đơn vị cố định (`unit-A001`, `unit-A002`...) và tính thống kê cho từng unit (`mean`, `median`, `std`, `min`, `max`, `pixel_count`), xuất `statistics.csv`, `statistics.json` và ảnh xem nhanh `ndvi-color-preview.png`.

9. **Phát hiện, gom cụm và xếp hạng bất thường (`anomalies/`)**
   - **Ngưỡng tuyệt đối (`absolute.py`)**: Đánh dấu các unit có NDVI thấp hơn ngưỡng cấu hình.
   - **Dị thường không gian (`spatial.py`)**: Tính điểm chuẩn hóa $z = \frac{x - \mu}{\sigma}$ để tìm các unit thấp bất thường so với toàn khu vực trong cùng chuyến khảo sát.
   - **Dị thường thời gian (`temporal.py`)**: So sánh sự sụt giảm NDVI của cùng một unit giữa chuyến khảo sát hiện tại và chuyến tham chiếu trước đó.
   - **Gom cụm & xếp hạng (`clustering.py`, `ranking.py`)**: Gộp các vùng bất thường liền kề thành Polygon, gán mức độ (`low`/`medium`/`high`), tính `priority_score` và tạo mã cảnh báo (`ALT-001`...).

10. **Xuất dữ liệu bàn giao cho Nhóm C (`export/`)**
    - Xuất `orthomosaic.tif`, `ndvi.tif`, `vegetation-mask.tif` (`geotiff_export.py`).
    - Xuất `alerts.geojson` chứa Polygon thực và đầy đủ các trường theo hợp đồng bàn giao với Nhóm C (`geojson_export.py`).
    - Xuất `statistics.csv`, `alerts.csv` (`csv_export.py`) và báo cáo tổng hợp `processing_report.json` (`report_export.py`).

11. **Tích hợp Pipeline một lệnh và viết Unit Test (`pipeline/runner.py`, `cli.py`, `tests/`)**
    - Kết nối toàn bộ các bước từ Bước 2 đến Bước 10 vào một lệnh CLI duy nhất (`process --input ... --config ...`), dừng và báo lỗi rõ ràng nếu bước bắt buộc thất bại.
    - Viết bộ kiểm thử tự động bằng `pytest` trong thư mục `tests/` cho từng module (đọc RAW, hiệu chuẩn, NDVI, mask, anomaly, xuất GeoTIFF/GeoJSON).