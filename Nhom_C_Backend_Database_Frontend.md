# NHÓM C --- BACKEND, DATABASE VÀ FRONTEND

> Dự án AgriScan \| Phụ trách nền tảng quản lý khu vực, khảo sát, kết
> quả xử lý, bản đồ, cảnh báo và kiểm tra thực địa.

## 1. Mục tiêu và nguyên tắc

Website cho phép quản lý plot/survey, tiếp nhận kết quả Nhóm B, xem
orthomosaic/NDVI, thống kê, cảnh báo, so sánh theo thời gian và lưu kiểm
tra thực địa.

-   Hệ thống sàng lọc bất thường, không chẩn đoán bệnh.
-   Raster lớn lưu dạng file/object storage; không lưu từng pixel trong
    bảng quan hệ.
-   Database lưu metadata, thống kê, đường dẫn file và geometry cần truy
    vấn.
-   Mock data phải đánh dấu DEMO.
-   Không cho client truyền đường dẫn tùy ý để backend đọc file máy chủ.

## 2. Phân công

  -----------------------------------------------------------------------
  Vai trò                             Công việc
  ----------------------------------- -----------------------------------
  C1 --- Backend/Database             PostgreSQL/PostGIS, migration,
                                      entity, repository, service, REST
                                      API, storage

  C2 --- Frontend/Map                 ReactJS, layout, dashboard,
                                      Plot/Survey, bản đồ, cảnh báo,
                                      FieldCheck
  -----------------------------------------------------------------------

Hai người thống nhất API contract, DTO và trạng thái nghiệp vụ trước khi
code sâu.

## 3. Công nghệ

  Thành phần     Công nghệ
  -------------- -----------------------
  Backend        Java Spring Boot
  Database       PostgreSQL + PostGIS
  ORM            Spring Data JPA
  Migration      Flyway
  Frontend       ReactJS + Vite
  Map            Leaflet hoặc MapLibre
  HTTP           Axios
  API test       Postman
  Backend test   JUnit/Mockito
  Container      Docker Compose

Chọn một thư viện bản đồ chính.

## 4. Cấu trúc thư mục

``` text
platform/
├── README.md
├── backend/
│   ├── pom.xml
│   └── src/
│       ├── main/
│       │   ├── java/com/agriscan/
│       │   │   ├── AgriScanApplication.java
│       │   │   ├── config/
│       │   │   ├── controller/
│       │   │   ├── service/
│       │   │   ├── repository/
│       │   │   ├── entity/
│       │   │   ├── dto/request/
│       │   │   ├── dto/response/
│       │   │   ├── mapper/
│       │   │   ├── exception/
│       │   │   └── security/
│       │   └── resources/
│       │       ├── application.yml
│       │       └── db/migration/
│       └── test/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── assets/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   ├── map/
│   │   │   ├── alert/
│   │   │   └── charts/
│   │   ├── pages/
│   │   │   ├── Dashboard/
│   │   │   ├── Plots/
│   │   │   ├── Surveys/
│   │   │   ├── Map/
│   │   │   ├── Alerts/
│   │   │   └── FieldChecks/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── contexts/
│   │   ├── types/
│   │   ├── utils/
│   │   ├── routes/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── package.json
│   └── vite.config.js
├── database/
│   ├── migrations/
│   ├── seed/
│   ├── schema.sql
│   └── README.md
└── storage/
    └── README.md
```

## 5. Database PostgreSQL/PostGIS

Tạo database:

``` sql
CREATE DATABASE agriscan;
```

Kết nối vào database:

``` sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

### 5.1. Quan hệ

``` text
PLOTS
  ├── SURVEYS
  │     ├── INDEX_VALUES
  │     └── ALERTS
  │            └── FIELD_CHECKS
  └── ANALYSIS_UNITS
         ├── INDEX_VALUES
         └── ALERTS
```

### 5.2. Bảng `plots`

  Cột          Kiểu                      Ý nghĩa
  ------------ ------------------------- -------------
  id           UUID                      PK
  name         VARCHAR(150)              Tên khu vực
  crop_type    VARCHAR(100)              Loại cây
  owner_name   VARCHAR(150)              Chủ sở hữu
  boundary     GEOMETRY(POLYGON, 4326)   Ranh giới
  area_m2      DOUBLE PRECISION          Diện tích
  created_at   TIMESTAMPTZ               Ngày tạo

### 5.3. Bảng `surveys`

  Cột                  Kiểu           Ý nghĩa
  -------------------- -------------- ---------------------
  id                   UUID           PK
  plot_id              UUID           FK plots
  survey_code          VARCHAR(100)   Mã survey
  started_at           TIMESTAMPTZ    Bắt đầu
  ended_at             TIMESTAMPTZ    Kết thúc
  acquisition_method   VARCHAR(30)    handheld/pole/fixed
  operator             VARCHAR(150)   Người thực hiện
  camera_model         VARCHAR(100)   Camera
  camera_filter        VARCHAR(50)    Filter
  processing_status    VARCHAR(30)    Trạng thái
  metadata_path        TEXT           Metadata path
  orthomosaic_path     TEXT           Orthomosaic path
  ndvi_path            TEXT           NDVI path
  created_at           TIMESTAMPTZ    Ngày tạo

### 5.4. Bảng `analysis_units`

  Cột            Kiểu                      Ý nghĩa
  -------------- ------------------------- -----------
  id             UUID                      PK
  plot_id        UUID                      FK plots
  unit_code      VARCHAR(100)              Mã unit
  geometry       GEOMETRY(POLYGON, 4326)   Polygon
  center_point   GEOMETRY(POINT, 4326)     Tâm
  area_m2        DOUBLE PRECISION          Diện tích

### 5.5. Bảng `index_values`

  Cột            Kiểu               Ý nghĩa
  -------------- ------------------ -------------------
  id             UUID               PK
  survey_id      UUID               FK surveys
  unit_id        UUID               FK analysis_units
  index_name     VARCHAR(30)        NDVI/GNDVI/SAVI
  mean_value     DOUBLE PRECISION   Mean
  median_value   DOUBLE PRECISION   Median
  std_value      DOUBLE PRECISION   Độ lệch chuẩn
  min_value      DOUBLE PRECISION   Min
  max_value      DOUBLE PRECISION   Max
  pixel_count    INTEGER            Pixel hợp lệ

### 5.6. Bảng `alerts`

  Cột               Kiểu                       Ý nghĩa
  ----------------- -------------------------- ---------------------------
  id                UUID                       PK
  survey_id         UUID                       FK surveys
  unit_id           UUID                       FK analysis_units
  alert_code        VARCHAR(100)               Mã cảnh báo
  anomaly_type      VARCHAR(30)                absolute/spatial/temporal
  index_name        VARCHAR(30)                Chỉ số
  observed_value    DOUBLE PRECISION           Giá trị hiện tại
  reference_value   DOUBLE PRECISION           Giá trị tham chiếu
  severity          VARCHAR(20)                low/medium/high
  priority_score    DOUBLE PRECISION           Điểm ưu tiên
  geometry          GEOMETRY(GEOMETRY, 4326)   Geometry
  status            VARCHAR(30)                Trạng thái
  reason            TEXT                       Lý do
  created_at        TIMESTAMPTZ                Ngày tạo

### 5.7. Bảng `field_checks`

  Cột          Kiểu                    Ý nghĩa
  ------------ ----------------------- ----------------
  id           UUID                    PK
  alert_id     UUID                    FK alerts
  inspector    VARCHAR(150)            Người kiểm tra
  checked_at   TIMESTAMPTZ             Thời gian
  conclusion   VARCHAR(50)             Kết luận
  notes        TEXT                    Ghi chú
  image_path   TEXT                    Ảnh thực địa
  location     GEOMETRY(POINT, 4326)   Vị trí
  created_at   TIMESTAMPTZ             Ngày tạo

### 5.8. Constraint và index

-   `surveys.survey_code` unique.
-   `(plot_id, unit_code)` unique.
-   `(survey_id, unit_id, index_name)` unique nếu mỗi survey chỉ có một
    kết quả chính thức/unit/index.
-   Tạo spatial index cho geometry thường truy vấn.
-   Dùng `TIMESTAMPTZ`.
-   Thống nhất SRID; kiểm tra chuyển CRS khi tính diện tích.
-   Chọn quy tắc xóa phù hợp, không xóa cascade lịch sử ngoài chủ đích.

## 6. Flyway migration

Đặt trong `backend/src/main/resources/db/migration/`:

``` text
V1__create_plots.sql
V2__create_surveys.sql
V3__create_analysis_units.sql
V4__create_index_values.sql
V5__create_alerts.sql
V6__create_field_checks.sql
```

Mỗi migration tạo bảng, PK/FK, constraints và spatial index. Kiểm tra
chạy từ database sạch.

``` yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/agriscan
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  jpa:
    hibernate:
      ddl-auto: validate
    show-sql: false
  flyway:
    enabled: true
```

Không commit mật khẩu. Dùng biến môi trường hoặc `.env` không đưa lên
Git.

## 7. Backend Spring Boot

Package:

``` text
com.agriscan
├── config
├── controller
├── service
├── repository
├── entity
├── dto/request
├── dto/response
├── mapper
├── exception
└── security
```

Tạo entity cho Plot, Survey, AnalysisUnit, IndexValue, Alert,
FieldCheck. Không trả entity trực tiếp; dùng DTO để tránh vòng lặp JPA
và kiểm soát dữ liệu.

Repository xử lý truy vấn; truy vấn không gian dùng native query/PostGIS
khi cần và phải kiểm thử CRS.

Service xử lý CRUD plot, tạo survey, kiểm tra quan hệ, nhập kết quả, lưu
thống kê/cảnh báo, tạo field check, cập nhật trạng thái.

Controller tiếp nhận request, validate, gọi service và trả response;
không đặt toàn bộ nghiệp vụ trong controller.

## 8. REST API

  Method   Endpoint                                 Chức năng
  -------- ---------------------------------------- ---------------------
  GET      `/api/plots`                             Danh sách plot
  POST     `/api/plots`                             Tạo plot
  GET      `/api/plots/{id}`                        Chi tiết
  PUT      `/api/plots/{id}`                        Cập nhật
  DELETE   `/api/plots/{id}`                        Xóa nếu phù hợp
  GET      `/api/plots/{id}/surveys`                Lịch sử survey
  POST     `/api/surveys`                           Tạo survey
  GET      `/api/surveys/{id}`                      Chi tiết survey
  GET      `/api/surveys/{id}/results`              Kết quả
  POST     `/api/surveys/{id}/processing-results`   Nhận kết quả B
  GET      `/api/surveys/{id}/alerts`               Cảnh báo survey
  GET      `/api/alerts`                            Danh sách
  GET      `/api/alerts/{id}`                       Chi tiết
  PATCH    `/api/alerts/{id}/status`                Cập nhật trạng thái
  POST     `/api/alerts/{id}/field-checks`          Gửi kiểm tra
  GET      `/api/alerts/{id}/field-checks`          Lịch sử kiểm tra

Quy tắc: DTO request/response; validation; phân trang/lọc; lỗi thống
nhất; không trả đường dẫn filesystem; kiểm tra quyền; alert phải liên
kết đúng survey/unit/plot.

Response cảnh báo mẫu:

``` json
{
  "content": [
    {
      "id": "alert-001",
      "alertCode": "ALT-001",
      "surveyId": "survey-001",
      "unitCode": "unit-A002",
      "indexName": "NDVI",
      "observedValue": 0.40,
      "referenceValue": 0.69,
      "anomalyType": "temporal",
      "severity": "high",
      "priorityScore": 82.5,
      "status": "PENDING",
      "reason": "NDVI decreased compared with previous survey"
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1
}
```

## 9. Nhận kết quả Nhóm B

Raster lớn (`orthomosaic.tif`, `ndvi.tif`, `vegetation-mask.tif`) lưu
file/object storage. Database lưu metadata, đường dẫn, CRS, thống kê,
cảnh báo và geometry.

``` text
AgriScan-Storage/
└── plots/plot-A/surveys/survey-001/
    ├── orthomosaic.tif
    ├── ndvi.tif
    ├── statistics.csv
    ├── statistics.json
    ├── alerts.geojson
    └── processing_report.json
```

API upload:

``` http
POST /api/surveys/{id}/processing-results
Content-Type: multipart/form-data
```

Các phần: `orthomosaic`, `ndvi`, `statistics`, `alerts`,
`processingReport`.

Backend: 1. Xác thực survey. 2. Kiểm tra định dạng/kích thước. 3. Sinh
đường dẫn lưu file phía server. 4. Validate JSON/GeoJSON. 5. Kiểm tra
survey ID/unit ID. 6. Lưu thống kê. 7. Lưu cảnh báo. 8. Cập nhật
processing status. 9. Trả import report.

Không nhận đường dẫn filesystem tùy ý từ client. Nếu pipeline và backend
dùng chung storage, có thể tạo script import gọi service/API; cần log và
chống nhập trùng.

## 10. Phục vụ raster trên bản đồ

Không tải toàn bộ GeoTIFF lớn vào trình duyệt. Thử raster tile service,
chuyển raster thành tile, server GIS chuyên dụng hoặc giải pháp demo nhỏ
sau khi đo hiệu năng.

Thử sớm với file thật: CRS, bounding box, kích thước, band, NoData,
tile, CORS và URL.

## 11. Frontend ReactJS

``` bash
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install axios react-router-dom leaflet react-leaflet
```

Nếu chọn MapLibre thì cài thư viện tương ứng thay cho React Leaflet.

Cấu trúc:

``` text
frontend/src/
├── assets/
├── components/
│   ├── layout/
│   ├── map/
│   ├── alert/
│   └── charts/
├── pages/
│   ├── Dashboard/
│   ├── Plots/
│   ├── Surveys/
│   ├── Map/
│   ├── Alerts/
│   └── FieldChecks/
├── services/
├── hooks/
├── contexts/
├── types/
├── utils/
├── routes/
├── App.jsx
└── main.jsx
```

Tạo `services/apiClient.js` dùng Axios: base URL từ env, timeout,
interceptor lỗi, token nếu có xác thực. Không hardcode URL production.

`.env.example`:

``` env
VITE_API_BASE_URL=http://localhost:8080/api
```

## 12. Giao diện

### Dashboard

Tổng plot/survey/alert; alert theo severity; alert chờ kiểm tra; NDVI
trung bình theo thời gian; cảnh báo mới.

### Quản lý Plot

Danh sách/tìm kiếm/lọc; tạo/sửa; ranh giới bản đồ; lịch sử survey.

### Quản lý Survey

Danh sách; thời gian; camera/filter; trạng thái xử lý; chi tiết; bản đồ;
processing report.

### Bản đồ

Layer ranh giới plot, orthomosaic, NDVI, vegetation mask, alert
polygons, field-check points. Có zoom/pan, bật tắt layer, chú giải, chọn
survey, chọn layer, click alert và focus map.

### Danh sách/chi tiết cảnh báo

Lọc plot/survey/severity/status/thời gian; sắp xếp priority; phân trang.
Chi tiết gồm alert code, plot, survey, unit, loại bất thường, chỉ số,
observed/reference, severity, priority, reason, geometry và lịch sử kiểm
tra.

### So sánh thời gian

Chọn plot, survey hiện tại và tham chiếu; hiển thị hai thời điểm, thay
đổi chỉ số và vùng thay đổi; cảnh báo nếu hai survey không đủ điều kiện
so sánh.

### Field Check

Form gồm alert ID, inspector, thời gian, kết luận, ghi chú, ảnh thực
địa, vị trí GPS nếu có.

## 13. Trạng thái cảnh báo

``` text
PENDING
ASSIGNED
INSPECTING
VERIFIED
DISMISSED
```

  Trạng thái   Ý nghĩa
  ------------ ---------------------------------------
  PENDING      Chưa giao
  ASSIGNED     Đã giao
  INSPECTING   Đang kiểm tra
  VERIFIED     Người kiểm tra xác nhận có bất thường
  DISMISSED    Đã kiểm tra nhưng không xác nhận

VERIFIED không đồng nghĩa chẩn đoán bệnh.

Danh mục FieldCheck có thể gồm `NORMAL`, `WATER_STRESS`,
`NUTRIENT_STRESS`, `PEST_OR_DISEASE_SUSPECTED`, `OTHER`. Đây là ghi nhận
kiểm tra, không phải chẩn đoán tự động.

## 14. Mock data

``` text
frontend/src/mock/
├── plots.mock.json
├── surveys.mock.json
├── alerts.mock.json
├── statistics.mock.json
└── alerts.mock.geojson
```

Gắn nhãn DEMO/MOCK; không trộn mock vào production; không báo cáo mock
là kết quả thật; giữ schema giống API contract; thay mock service bằng
API thật khi tích hợp.

## 15. Kiểm thử

Backend: CRUD Plot, tạo Survey, FK, import result, validate GeoJSON, lưu
Alert, cập nhật status, FieldCheck, phân trang/lọc, truy vấn không gian.

Frontend: điều hướng, loading/error/empty, form CRUD, lọc/phân trang,
hiển thị layer, chọn alert/focus map, upload ảnh, geometry/NoData thiếu.

Tích hợp: nhận file B; import backend; kiểm tra số alert; kiểm tra
geometry PostGIS; mở bản đồ; đối chiếu QGIS/web; tạo FieldCheck; kiểm
tra dữ liệu lưu.

## 16. Bảo mật/vận hành

-   Không commit mật khẩu/API key.
-   Validate file upload, loại file và dung lượng.
-   Sinh tên file phía server.
-   Chống path traversal.
-   Phân quyền nếu có nhiều vai trò.
-   Không xóa lịch sử tùy tiện.
-   Log lỗi import.
-   Sao lưu DB và storage.
-   Cấu hình CORS theo môi trường.

## 17. Checklist nghiệm thu

-   [ ] PostgreSQL/PostGIS hoạt động.
-   [ ] Flyway chạy từ database sạch.
-   [ ] CRUD Plot.
-   [ ] Tạo/tra cứu Survey.
-   [ ] API nhận kết quả B.
-   [ ] Lưu file raster và metadata.
-   [ ] Lưu thống kê/cảnh báo.
-   [ ] Hiển thị orthomosaic.
-   [ ] Hiển thị NDVI.
-   [ ] Hiển thị polygon cảnh báo.
-   [ ] Lọc/chi tiết cảnh báo.
-   [ ] So sánh survey.
-   [ ] Tạo FieldCheck.
-   [ ] Cập nhật trạng thái.
-   [ ] Có loading/error/empty state.
-   [ ] Có test và tài liệu cài đặt.

## 18. Kế hoạch 16 tuần

  Tuần   Công việc                    Sản phẩm
  ------ ---------------------------- ----------------------
  1      Chốt stack, contract, DB     ERD/contract
  2      Khởi tạo Spring Boot/React   Skeleton
  3      Migration, Plot/Survey API   API cơ bản
  4      Storage và API kết quả       Upload/import
  5      Thử hiển thị orthomosaic     Map prototype
  6      API thống kê                 Statistics API
  7      Alert API, dashboard         Alert list
  8      Cảnh báo trên bản đồ         Alert map
  9      So sánh survey               Comparison
  10     Biểu đồ thời gian            Time-series
  11     FieldCheck API/form          Workflow
  12     Trạng thái, tích hợp A       Verification
  13     Tích hợp toàn hệ thống       Demo
  14     Kiểm thử                     Test report
  15     Tài liệu                     User/developer guide
  16     Bàn giao                     Website/source

## 19. Git và báo cáo

Branch:

``` text
feature/group-c/database
feature/group-c/backend-api
feature/group-c/file-storage
feature/group-c/frontend-layout
feature/group-c/frontend-map
feature/group-c/field-check
```

Commit:

``` text
feat(platform): create plot API
feat(platform): add PostGIS alert geometry
feat(frontend): display NDVI layer
feat(frontend): add field-check form
test(platform): validate processing import
```

API contract thay đổi phải báo B và C2. Không hardcode mock trong
component, không commit secret/raster lớn.

Báo cáo cuối: kiến trúc, ERD, PostGIS, API, tiếp nhận dữ liệu B,
storage/raster serving, giao diện, luồng cảnh báo/field-check, kiểm thử
và hạn chế.
