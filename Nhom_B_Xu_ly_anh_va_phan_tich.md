# NHÓM B --- XỬ LÝ ẢNH VÀ PHÂN TÍCH

> Dự án AgriScan \| Phụ trách đọc RAW, hiệu chỉnh ảnh, ghép ảnh, NDVI,
> thống kê và phát hiện bất thường.

## 1. Mục tiêu và nguyên tắc

Nhận dữ liệu khảo sát từ Nhóm A và tạo ảnh/kênh phổ đã giải mã,
reflectance đã hiệu chỉnh, orthomosaic GeoTIFF nếu đủ điều kiện, NDVI
GeoTIFF, vegetation mask, thống kê, GeoJSON cảnh báo và processing
report.

Nguyên tắc: - Không mặc định `rawpy` hỗ trợ RAW MAPIR. - Không đoán thứ
tự band, filter hoặc bước sóng. - RAW không đồng nghĩa reflectance. -
Không dùng công thức hiệu chỉnh chưa xác thực để tuyên bố phản xạ
chuẩn. - NDVI chỉ hợp lệ khi Red/NIR đúng kênh, đồng đăng ký và dữ liệu
đầu vào phù hợp. - Không chẩn đoán bệnh từ NDVI; cảnh báo là vùng cần
kiểm tra. - Ghi version code/config/input. - Thiếu dữ liệu bắt buộc thì
báo lỗi rõ ràng.

## 2. Phân công

  -----------------------------------------------------------------------
  Vai trò                             Công việc
  ----------------------------------- -----------------------------------
  B1 --- Ảnh/hiệu chỉnh               RAW reader, giải mã, tách band,
                                      vignetting, reflectance, mosaicking

  B2 --- Phân tích                    NDVI, mask, thống kê, anomaly,
                                      clustering, export
  -----------------------------------------------------------------------

B1 bàn giao rõ band mapping, kiểu dữ liệu và metadata cho B2.

## 3. Công cụ và cài đặt

  Công cụ                    Mục đích
  -------------------------- ---------------------------
  Python 3.11                Xử lý
  NumPy/SciPy                Mảng, thống kê
  OpenCV                     Xử lý ảnh
  Rasterio/GDAL              GeoTIFF
  GeoPandas/Shapely/PyProj   Vector/CRS
  Pandas                     Bảng dữ liệu
  Matplotlib                 Preview/biểu đồ
  PyYAML                     Cấu hình
  Typer                      CLI
  pytest/Ruff                Test/lint
  rawpy                      Thử đọc RAW, cần xác minh
  OpenDroneMap               Thử nghiệm ghép ảnh
  QGIS                       Kiểm tra GIS

``` bash
python -m venv .venv
.venv\Scripts\activate
pip install numpy scipy opencv-python rasterio geopandas shapely pyproj pandas matplotlib pyyaml pytest typer ruff
pip install rawpy scikit-learn
python -c "import numpy, rasterio, geopandas; print('OK')"
```

## 4. Cấu trúc thư mục

``` text
processing/
├── README.md
├── requirements.txt
├── pyproject.toml
├── configs/
│   ├── default.yaml
│   ├── calibration.yaml
│   ├── indices.yaml
│   └── anomaly.yaml
├── src/agriscan/
│   ├── __init__.py
│   ├── cli.py
│   ├── io/
│   │   ├── raw_reader.py
│   │   ├── metadata_reader.py
│   │   ├── image_validator.py
│   │   └── raster_io.py
│   ├── calibration/
│   │   ├── decoder.py
│   │   ├── band_extractor.py
│   │   ├── vignetting.py
│   │   ├── reflectance.py
│   │   └── quality_check.py
│   ├── mosaicking/
│   │   ├── odm_runner.py
│   │   ├── georeference.py
│   │   └── mosaic_quality.py
│   ├── indices/
│   │   ├── ndvi.py
│   │   ├── gndvi.py
│   │   ├── savi.py
│   │   ├── masking.py
│   │   └── statistics.py
│   ├── anomalies/
│   │   ├── absolute.py
│   │   ├── spatial.py
│   │   ├── temporal.py
│   │   ├── clustering.py
│   │   └── ranking.py
│   ├── export/
│   │   ├── geotiff_export.py
│   │   ├── geojson_export.py
│   │   ├── csv_export.py
│   │   └── report_export.py
│   └── pipeline/
│       ├── runner.py
│       └── steps.py
├── tests/
│   ├── test_raw_reader.py
│   ├── test_calibration.py
│   ├── test_ndvi.py
│   ├── test_masking.py
│   ├── test_anomalies.py
│   └── test_export.py
└── examples/
    ├── sample-metadata.json
    └── synthetic-data/
```

Dữ liệu thật nằm ngoài Git trong thư mục khảo sát.

## 5. Đầu vào từ Nhóm A

Một survey cần có `metadata.json`, `raw/`, `calibration/`, `logs/` và
`gcp/` nếu có.

`io/image_validator.py` kiểm tra: 1. Thư mục tồn tại. 2. Metadata đúng
schema. 3. Survey ID/Plot ID hợp lệ. 4. Model/filter camera được xác
nhận. 5. Có RAW. 6. Có ảnh hiệu chỉnh theo quy trình. 7.
Manifest/checksum. 8. EXIF/GPS. 9. Kích thước/định dạng. 10. File trùng
hoặc hỏng.

Lỗi nghiêm trọng phải dừng pipeline và trả danh sách lỗi cho A.

## 6. Bước 1 --- Đọc RAW

File: `io/raw_reader.py`.

``` python
def read_raw(file_path):
    # Đọc RAW bằng decoder đã xác nhận; trả dữ liệu và metadata.
    raise NotImplementedError
```

Thực hiện: kiểm tra file; xác định định dạng thực tế; thử decoder tương
thích; đọc kích thước/bit depth/cấu trúc kênh; kiểm tra pixel; ghi
decoder/version; báo lỗi nếu không đọc được.

Không mặc định `rawpy` tương thích với mọi RAW MAPIR. Nếu không tương
thích, kiểm tra công cụ MAPIR hoặc decoder được nhà sản xuất hỗ trợ.

### 6.1. Xác nhận band

  Band    Bước sóng/filter      Nguồn xác nhận   Trạng thái
  ------- --------------------- ---------------- ------------------
  Red     Theo camera thực tế   Model/tài liệu   Chưa/đã xác nhận
  NIR     Theo camera thực tế   Model/tài liệu   Chưa/đã xác nhận
  Green   Theo camera thực tế   Model/tài liệu   Chưa/đã xác nhận

Không gán tên band theo vị trí mảng nếu chưa xác nhận.

## 7. Bước 2 --- Tách band

File: `calibration/band_extractor.py`.

Nhận dữ liệu đã giải mã; ánh xạ band theo cấu trúc cảm biến/filter đã
xác nhận; tách band; kiểm tra kích thước/kiểu dữ liệu; ghi metadata;
xuất ảnh trung gian.

Ví dụ:

``` text
processed/calibration/IMG_0001/
├── red.tif
├── green.tif
└── nir.tif
```

Chỉ tạo band thực sự có trên camera.

## 8. Bước 3 --- Vignetting

File: `calibration/vignetting.py`.

1.  Xác định dữ liệu và cách giải mã.
2.  Xác định phương pháp phù hợp cảm biến.
3.  Đối chiếu tài liệu thiết bị/quy trình tham chiếu.
4.  Tạo mô-đun có cấu hình.
5.  Lưu tham số.
6.  So sánh trước/sau bằng dữ liệu kiểm tra.
7.  Ghi báo cáo.

Không dùng mặt nạ tự đặt rồi coi là hiệu chuẩn thiết bị đã được xác
thực.

## 9. Bước 4 --- Hiệu chỉnh phản xạ

File: `calibration/reflectance.py`.

Đầu vào: RAW khu vực, RAW tấm hiệu chỉnh trước/sau, metadata
camera/filter, thông tin target và thông số/quy trình được xác nhận.

Các bước: 1. Đọc RAW khu vực. 2. Đọc RAW target. 3. Kiểm tra
model/filter. 4. Áp dụng quy trình hiệu chuẩn được xác nhận. 5. Kiểm tra
giá trị, NoData, pixel bất thường. 6. Xuất phản xạ theo band. 7. Lưu
tham số và nguồn hiệu chuẩn. 8. Tạo báo cáo.

Không tự đặt công thức tuyến tính nếu chưa xác nhận cảm biến, target và
quy trình MAPIR.

### 9.1. Kiểm chứng

Thử cùng vật thể ở ba thời điểm theo kế hoạch.

\[ D(%)=`\frac{|R_i-R_{ref}|}{R_{ref}}`{=tex}`\times100`{=tex} \]

Mục tiêu dự án là sai lệch dưới 5% trong phép thử. Đây là tiêu chí cần
đo, không được ghi đạt khi chưa có số liệu.

  Lần đo   Thời gian         Red       NIR   Sai lệch
  -------- ----------- --------- --------- ----------
  1        Sáng          Đo thật   Đo thật       Tính
  2        Trưa          Đo thật   Đo thật       Tính
  3        Chiều         Đo thật   Đo thật       Tính

## 10. Bước 5 --- Orthomosaic

File: `mosaicking/odm_runner.py`.

OpenDroneMap là công cụ thử nghiệm ghép ảnh; không mặc định dữ liệu đa
phổ được bảo toàn đúng.

1.  Kiểm tra số lượng/chất lượng ảnh.
2.  Kiểm tra EXIF/GPS.
3.  Xác nhận dữ liệu đủ điều kiện ghép.
4.  Chuẩn bị đầu vào.
5.  Chạy ODM.
6.  Kiểm tra log/ảnh thất bại.
7.  Kiểm tra CRS, transform, coverage, vùng thủng.
8.  Kiểm tra đồng đăng ký giữa band.
9.  Xuất báo cáo.

Đầu ra:

``` text
processed/mosaic/
├── orthomosaic.tif
├── odm-output/
├── odm-log.txt
└── mosaic-quality.json
```

Mục tiêu nghiệm thu: ít nhất 90% ảnh được sử dụng và không có vùng thủng
trong vùng mục tiêu. Phải chứng minh bằng log và kiểm tra thực tế.

Nếu ODM không bảo toàn dữ liệu đa phổ hoặc band không đồng đăng ký, tách
quy trình ghép hình học và đăng ký band. Không dùng JPG làm raster phân
tích.

## 11. Bước 6 --- NDVI

File: `indices/ndvi.py`.

\[ NDVI=`\frac{NIR-Red}{NIR+Red}`{=tex} \]

Điều kiện: Red/NIR đúng band; raster cùng kích thước, CRS, transform; đã
đồng đăng ký; phản xạ đầu vào phù hợp; xử lý NoData và mẫu số 0.

``` python
import numpy as np

def calculate_ndvi(red, nir):
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)
    denominator = nir + red
    ndvi = np.full(red.shape, np.nan, dtype=np.float32)
    valid = np.isfinite(red) & np.isfinite(nir)
    valid &= denominator != 0
    ndvi[valid] = (nir[valid] - red[valid]) / denominator[valid]
    return ndvi
```

Đây là hàm tính trên mảng; cần triển khai riêng đọc raster, alignment,
mask và ghi GeoTIFF.

Unit test cần kiểm tra kết quả mẫu, mẫu số 0, NaN/NoData, khác kích
thước, CRS/transform không khớp và giá trị đầu ra. Không tính NDRE nếu
camera không có Red-Edge; chỉ tính GNDVI/SAVI nếu band cần thiết tồn tại
và đã xác nhận.

## 12. Bước 7 --- Mask và chia vùng

File: `indices/masking.py`.

Đọc NDVI và ranh giới plot; tạo mask hợp lệ; thử ngưỡng thực vật; loại
NoData; lưu `vegetation-mask.tif`; ghi ngưỡng/phương pháp.

Ngưỡng NDVI \> 0,2 chỉ là giá trị thử nghiệm ban đầu, phải đánh giá trên
dữ liệu thực tế.

Chia unit có ID ổn định, ví dụ `unit-A001`, `unit-A002`. Mỗi unit có
polygon, mã và diện tích. So sánh thời gian cần giữ hình học/ánh xạ unit
nhất quán.

## 13. Bước 8 --- Thống kê

File: `indices/statistics.py`.

Tính mean, median, standard deviation, min/max, percentile, pixel count
hợp lệ theo plot/unit.

``` csv
unit_id,mean_ndvi,median_ndvi,std_ndvi,pixel_count
unit-A001,0.65,0.68,0.08,1250
unit-A002,0.42,0.44,0.12,1180
```

Đây là số minh họa.

Đầu ra:

``` text
processed/indices/
├── ndvi.tif
├── vegetation-mask.tif
├── ndvi-statistics.csv
├── ndvi-statistics.json
└── ndvi-color-preview.png
```

GeoTIFF là dữ liệu phân tích; PNG chỉ là preview. Raster phải có CRS,
transform, NoData và kiểu dữ liệu.

## 14. Bước 9 --- Phát hiện bất thường

Mục tiêu là sàng lọc vùng cần kiểm tra, không chẩn đoán bệnh.

### 14.1. Ngưỡng tuyệt đối

File: `anomalies/absolute.py`: đọc thống kê; đọc ngưỡng config; so sánh;
tạo candidate alert; ghi lý do.

``` yaml
absolute:
  enabled: true
  index: NDVI
  threshold: 0.35
  comparison: less_than
```

0,35 chỉ là ngưỡng thử nghiệm, cần hiệu chỉnh theo cây và dữ liệu.

### 14.2. Dị thường không gian

File: `anomalies/spatial.py`.

\[ z=`\frac{x-\mu}{\sigma}`{=tex} \]

So sánh unit với phân bố unit trong cùng plot/survey. Xử lý `sigma = 0`,
unit không hợp lệ, outlier và phân bố lệch. Ghi phương pháp/ngưỡng;
không so sánh khu vực khác điều kiện một cách máy móc.

### 14.3. Dị thường thời gian

File: `anomalies/temporal.py`.

Chọn survey hiện tại/tham chiếu; kiểm tra cùng plot; kiểm tra hiệu chỉnh
tương thích; kiểm tra raster đồng đăng ký; ghép unit; tính thay đổi;
đánh dấu giảm đáng chú ý; ghi survey tham chiếu và phương pháp.

Chỉ chạy khi có ít nhất hai survey so sánh được. Nếu điều kiện khác biệt
đáng kể, ghi hạn chế hoặc không chạy.

### 14.4. Xếp hạng và gom cụm

`ranking.py` có thể kết hợp mức lệch, diện tích và số lần lặp. Trọng số
phải nằm trong config và được đánh giá; không coi trọng số ban đầu là
khoa học đã xác nhận.

`clustering.py` gom vùng liền kề thành polygon, gắn mã, loại bất thường,
severity, priority score và geometry đúng CRS.

## 15. Bước 10 --- GeoJSON

File: `export/geojson_export.py`.

``` json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": []
      },
      "properties": {
        "alert_code": "ALT-001",
        "survey_id": "survey-001",
        "unit_id": "unit-A002",
        "index_name": "NDVI",
        "observed_value": 0.40,
        "reference_value": 0.69,
        "anomaly_type": "temporal",
        "severity": "high",
        "priority_score": 82.5,
        "reason": "NDVI decreased compared with previous survey"
      }
    }
  ]
}
```

Coordinates phải lấy từ polygon thực; không để geometry rỗng trong kết
quả bàn giao. Kiểm tra CRS, geometry validity và quan hệ survey/unit.

## 16. Bước 11 --- Pipeline một lệnh

Tạo `pipeline/runner.py` và `cli.py`.

``` bash
python -m agriscan.cli process \
  --input /data/plot-A/survey_2026-11-06_001 \
  --config configs/default.yaml
```

Pipeline: validate input → read metadata → decode RAW → extract bands →
calibrate → mosaic nếu đủ điều kiện → NDVI → mask → statistics →
anomalies → export → report.

Nếu bước bắt buộc thất bại, pipeline phải dừng hoặc ghi trạng thái lỗi;
không báo completed khi thiếu sản phẩm chính.

## 17. Cấu trúc đầu ra

``` text
processed/
├── calibration/reflectance/
├── mosaic/
│   ├── orthomosaic.tif
│   ├── odm-log.txt
│   └── mosaic-quality.json
├── indices/
│   ├── ndvi.tif
│   ├── vegetation-mask.tif
│   ├── statistics.csv
│   └── statistics.json
├── anomalies/
│   ├── alerts.geojson
│   └── alerts.csv
└── reports/
    └── processing_report.json
```

Processing report cần survey ID, pipeline/config version, trạng thái,
thời gian, số ảnh input/used/failed, CRS, output paths và warnings. Chưa
có số liệu thì để null.

## 18. Hợp đồng bàn giao Nhóm C

  Trường            Kiểu               Ý nghĩa
  ----------------- ------------------ ---------------------------
  alert_code        string             Mã cảnh báo
  survey_id         string             Survey
  unit_id           string             Đơn vị phân tích
  index_name        string             NDVI/GNDVI/SAVI
  observed_value    number             Giá trị quan sát
  reference_value   number/null        Giá trị tham chiếu
  anomaly_type      string             absolute/spatial/temporal
  severity          string             low/medium/high
  priority_score    number             Điểm ưu tiên
  geometry          GeoJSON geometry   Polygon
  reason            string             Lý do

Bàn giao orthomosaic, NDVI, mask, statistics CSV/JSON, alerts GeoJSON,
processing report và tài liệu band/CRS/NoData/kiểu dữ liệu.

## 19. Kiểm thử

Unit test: RAW reader, metadata thiếu trường, calibration/NoData, NDVI,
mask, anomaly với dữ liệu rỗng/sigma 0, GeoTIFF giữ CRS/transform,
GeoJSON geometry hợp lệ.

Integration: validate bộ dữ liệu mẫu; chạy pipeline; kiểm tra đầu ra; mở
raster/vector trong QGIS; đối chiếu unit ID với CSV; chạy lại cùng
input/config và so sánh.

Mock chỉ kiểm thử kỹ thuật, không được báo cáo là kiểm chứng thực địa.

## 20. Checklist nghiệm thu

-   [ ] RAW đọc được bằng decoder xác nhận.
-   [ ] Band mapping có căn cứ.
-   [ ] Reflectance có quy trình và báo cáo.
-   [ ] Mục tiêu sai lệch dưới 5% được kiểm tra bằng số liệu thật.
-   [ ] Orthomosaic có quality report.
-   [ ] NDVI đúng và có unit test.
-   [ ] Có mask/thống kê.
-   [ ] Có absolute và spatial anomaly.
-   [ ] Có temporal anomaly khi đủ dữ liệu.
-   [ ] GeoJSON đúng schema/CRS.
-   [ ] Pipeline chạy lại được.
-   [ ] Nhóm C xác nhận đọc được kết quả.

## 21. Kế hoạch 16 tuần

  Tuần   Công việc                                   Sản phẩm
  ------ ------------------------------------------- ------------------------
  1      Cài môi trường, kiểm tra RAW, dữ liệu giả   Môi trường
  2      RAW reader, metadata reader                 Mô-đun đọc
  3      Tách band, vignetting, reflectance          Hiệu chỉnh sơ bộ
  4      Kiểm chứng hiệu chỉnh                       Báo cáo G1
  5      Orthomosaic                                 GeoTIFF/quality
  6      NDVI, unit test                             NDVI
  7      Mask, unit, thống kê                        CSV/JSON
  8      Absolute/spatial anomaly                    GeoJSON
  9      Temporal anomaly                            Mô-đun
  10     Ranking, clustering, export                 Cảnh báo
  11     Đối chiếu field-check                       Báo cáo
  12     Điều chỉnh ngưỡng                           Config
  13     Pipeline tích hợp                           Demo
  14     Kiểm thử                                    Test report
  15     Tài liệu                                    Hướng dẫn
  16     Bàn giao                                    Source/pipeline/report

## 22. Git và báo cáo

Branch:

``` text
feature/group-b/raw-reader
feature/group-b/calibration
feature/group-b/mosaicking
feature/group-b/ndvi
feature/group-b/anomaly
feature/group-b/export
```

Commit:

``` text
feat(processing): add RAW reader
feat(processing): implement NDVI calculation
fix(processing): handle nodata pixels
test(processing): add reflectance validation tests
docs(processing): describe raster output contract
```

Không commit RAW/raster lớn. Không hardcode đường dẫn máy cá nhân. Dùng
YAML cho tham số. Báo cáo cuối gồm kiến trúc, giải mã RAW, band mapping,
hiệu chỉnh/kiểm chứng, ghép ảnh, NDVI/mask, anomaly, đối chiếu thực địa,
hiệu năng và hạn chế.
