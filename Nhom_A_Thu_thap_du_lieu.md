# NHÓM A --- THU THẬP DỮ LIỆU VÀ HIỆN TRƯỜNG

> Dự án AgriScan \| Phụ trách dữ liệu đầu vào, metadata, quy trình
> camera, GCP và kiểm chứng thực địa.

## 1. Mục tiêu và nguyên tắc

Nhóm A tạo bộ dữ liệu đầu vào đầy đủ, có thể kiểm tra và bàn giao cho
Nhóm B; đồng thời tiếp nhận cảnh báo để xác minh tại hiện trường.

**Sản phẩm:** SOP, RAW/JPG, ảnh tấm hiệu chỉnh trước/sau,
`metadata.json`, công cụ nhập ảnh, manifest/checksum, nhật ký khảo sát,
GCP (nếu có), phiếu kiểm tra thực địa.

-   Giai đoạn hiện tại không triển khai hoạt động bay/drone. Dùng camera
    cầm tay, gắn sào hoặc đặt cố định theo kế hoạch.
-   Không chỉnh sửa/ghi đè RAW gốc. JPG dùng xem trước/đối chiếu, không
    tự thay RAW trong phân tích đa phổ.
-   Không đoán model, filter, bước sóng, thứ tự band hoặc tọa độ.
-   Chưa đo thì ghi `null`, không điền số giả.
-   AgriScan sàng lọc bất thường, không chẩn đoán bệnh.

## 2. Phân công

  -----------------------------------------------------------------------
  Vai trò                             Công việc
  ----------------------------------- -----------------------------------
  A1 --- Camera/hiện trường           Kiểm tra camera, cấu hình, chụp
                                      ảnh, tấm hiệu chỉnh, giá/sào, GCP

  A2 --- Dữ liệu/công cụ              Metadata, script nhập ảnh,
                                      checksum, manifest, nhật ký, kiểm
                                      tra cấu trúc
  -----------------------------------------------------------------------

Cả hai cùng khảo sát. A1 tập trung camera; A2 ghi nhật ký và kiểm tra dữ
liệu tại hiện trường.

## 3. Công cụ và cài đặt

  -----------------------------------------------------------------------
  Công cụ                             Mục đích
  ----------------------------------- -----------------------------------
  MAPIR Survey3                       Camera đa phổ

  MAPIR Camera Control/công cụ MAPIR  Kiểm tra và xử lý theo hướng dẫn
  được hỗ trợ                         nhà sản xuất

  ExifTool                            Đọc EXIF, thời gian, GPS

  Python 3.11                         Metadata, nhập ảnh, kiểm tra dữ
                                      liệu

  VS Code                             Viết code

  Git/GitHub                          Quản lý code/tài liệu; không lưu
                                      ảnh lớn

  Excel/Google Sheets                 Nhật ký khảo sát

  QGIS                                Kiểm tra dữ liệu không gian

  pytest                              Kiểm thử script
  -----------------------------------------------------------------------

``` bash
python -m venv .venv
.venv\Scripts\activate
pip install pydantic questionary pandas openpyxl pytest
exiftool -ver
```

Cài ExifTool riêng theo hệ điều hành.

## 4. Cấu trúc thư mục

``` text
acquisition/
├── README.md
├── docs/
│   ├── SOP.md
│   ├── camera-setup.md
│   ├── field-survey-guide.md
│   ├── calibration-procedure.md
│   └── GCP-guide.md
├── metadata-tool/
│   ├── src/
│   │   ├── main.py
│   │   ├── metadata_generator.py
│   │   └── validators.py
│   ├── templates/metadata.template.json
│   ├── tests/
│   └── requirements.txt
├── data-importer/
│   ├── src/
│   │   ├── import_sd.py
│   │   ├── rename_images.py
│   │   ├── checksum.py
│   │   └── validate_survey.py
│   ├── tests/
│   └── requirements.txt
├── field-logs/
│   ├── survey-log-template.xlsx
│   └── field-check-template.xlsx
├── gcp/
│   ├── README.md
│   └── gcp-template.csv
└── experiments/
    ├── lab-01/
    ├── lab-02/
    ├── lab-03/
    ├── lab-04/
    └── lab-05/
```

Dữ liệu thực lưu ngoài Git:

``` text
AgriScan-Data/
└── plot-A/
    └── survey_2026-11-06_001/
        ├── metadata.json
        ├── raw/
        ├── calibration/
        ├── gcp/
        └── logs/
```

Mỗi lần khảo sát tại một plot có một `survey_id` riêng.

## 5. Quy trình thu thập

### 5.1. Trước buổi khảo sát

A1 kiểm tra camera, pin, thẻ nhớ, tấm hiệu chỉnh, sào/giá, máy kiểm tra
ảnh và dung lượng lưu trữ. A2 chuẩn bị `survey_id`, `plot_id`, mẫu
metadata, nhật ký và thư mục lưu trữ.

### 5.2. Kiểm tra camera

1.  Xác nhận model và filter thực tế.
2.  Kiểm tra chế độ ghi RAW/JPG.
3.  Chụp thử.
4.  Xác nhận RAW và JPG được tạo.
5.  Dùng ExifTool kiểm tra EXIF.
6.  Ghi cấu hình camera vào nhật ký.

Không thay đổi thông số camera giữa các lần khảo sát so sánh nếu không
có lý do và ghi nhận thay đổi.

### 5.3. Tấm hiệu chỉnh trước

Thực hiện theo hướng dẫn nhà sản xuất; chụp RAW và JPG; lưu trong
`calibration/`; đặt tên `target_before.RAW`, `target_before.JPG`; ghi
thời gian.

### 5.4. Chụp khu vực

-   Chỉ dùng phương pháp cầm tay, sào hoặc giá cố định.
-   Ghi độ cao và phương pháp thực tế.
-   Giữ quy trình chụp nhất quán.
-   Ghi ánh sáng, thời tiết và tình trạng khu vực.
-   Chụp đủ vùng mục tiêu.
-   Nếu dự định ghép ảnh, ghi lại đường chụp và vùng chồng lấn theo kế
    hoạch thử nghiệm.
-   Không tự khai báo overlap nếu chưa đo/kiểm tra.

### 5.5. Tấm hiệu chỉnh sau

Lặp lại quy trình, lưu `target_after.RAW` và `target_after.JPG`. Nếu
thiếu ảnh trước/sau, đánh dấu bộ dữ liệu cần kiểm tra.

### 5.6. Sao lưu

1.  Sao chép từ thẻ nhớ, không di chuyển.
2.  Tạo checksum SHA-256.
3.  Kiểm tra số lượng RAW/JPG.
4.  Sao lưu vị trí thứ hai.
5.  Chỉ xóa thẻ sau khi xác minh bản sao.

## 6. Metadata

Ví dụ `metadata.json`:

``` json
{
  "survey_id": "2026-11-06_plot-A_001",
  "plot_id": "plot-A",
  "datetime_start": "2026-11-06T08:30:00+07:00",
  "datetime_end": "2026-11-06T09:10:00+07:00",
  "operator": "Nguyen Van A",
  "acquisition_method": "pole",
  "camera": {
    "model": "MAPIR Survey3",
    "filter": "VERIFY_ACTUAL_FILTER",
    "bands": {
      "red": null,
      "green": null,
      "nir": null
    },
    "serial": null
  },
  "height_m": null,
  "gsd_cm": null,
  "overlap": {
    "forward": null,
    "side": null
  },
  "weather": {
    "sky": "clear",
    "notes": ""
  },
  "calibration_target": {
    "model": null,
    "before": "calibration/target_before.RAW",
    "after": "calibration/target_after.RAW"
  },
  "image_count": 0
}
```

Đây là mẫu cấu trúc, không phải cấu hình camera được xác nhận. Bước sóng
phải lấy từ model/filter thực tế.

### 6.1. Validation

-   `survey_id`, `plot_id` không rỗng.
-   Thời gian ISO 8601; bắt đầu không sau kết thúc.
-   `acquisition_method`: `handheld`, `pole`, `fixed`.
-   `height_m`: số dương hoặc null.
-   `image_count`: số nguyên không âm.
-   Model/filter phải được xác nhận.
-   Đường dẫn calibration phải tồn tại hoặc được đánh dấu thiếu.

### 6.2. Metadata tool

`metadata-tool/src/main.py` hỏi thông tin khảo sát, kiểm tra đầu vào,
gọi `metadata_generator.py`, validate bằng `validators.py`, ghi
`metadata.json` và hiển thị lỗi rõ ràng.

## 7. Công cụ nhập ảnh

Tạo `data-importer/src/import_sd.py`.

Chức năng: nhận thư mục nguồn/đích; quét file; phân loại RAW/JPG; sao
chép không sửa nội dung; đổi tên nếu cần; lưu tên gốc trong manifest;
tạo SHA-256; kiểm tra cặp RAW/JPG; kiểm tra ảnh hiệu chỉnh; tạo báo cáo.

Manifest mẫu:

``` csv
original_name,stored_name,type,size_bytes,sha256
DSC_0001.RAW,IMG_0001.RAW,RAW,123456,...
DSC_0001.JPG,IMG_0001.JPG,JPG,12345,...
```

Báo cáo mẫu:

``` json
{
  "survey_id": "2026-11-06_plot-A_001",
  "import_status": "needs_review",
  "raw_count": 142,
  "jpg_count": 142,
  "missing_jpg": [],
  "missing_raw": [],
  "calibration_before_exists": true,
  "calibration_after_exists": true,
  "checksum_verified": true
}
```

Không tự đặt `success` nếu thiếu file hoặc checksum không khớp.

## 8. Nhật ký khảo sát

Tạo Excel có các cột: Survey ID, Plot ID, ngày giờ, người chụp,
camera/filter, phương pháp, độ cao, thời tiết, tình trạng cây, tình
trạng đất, tấm hiệu chỉnh, số ảnh, sự cố và ghi chú.

## 9. GCP

GCP hỗ trợ định vị/đánh giá hình học nếu có thiết bị và phương pháp đo
phù hợp.

``` csv
gcp_id,x,y,z,crs,description
GCP01,,,,"EPSG:XXXX",Corner_A
GCP02,,,,"EPSG:XXXX",Corner_B
```

Ghi tọa độ đo thực tế, CRS và đơn vị. Không dùng tọa độ mẫu làm dữ liệu
thật; không trộn kinh/vĩ độ với tọa độ phẳng nếu chưa chuyển CRS.

## 10. Lab và khảo sát theo thời gian

Lab 4 phải bắt đầu từ tuần 1 vì cần chuỗi quan sát nhiều tuần. Với khảo
sát lặp: dùng cùng plot và quy trình chụp; tạo survey ID riêng; lưu ảnh
hiệu chỉnh; ghi thời gian/thời tiết/tình trạng cây; không tự thay đổi
điều kiện thí nghiệm ngoài kế hoạch được duyệt.

## 11. Xác minh cảnh báo

Khi nhận cảnh báo từ Nhóm C: nhận `alert_id`, `survey_id`, `plot_id`,
`unit_id`; xem vị trí/lý do; kiểm tra đúng khu vực; ghi nhận quan sát;
chụp ảnh nếu được phép; ghi tọa độ nếu có; chọn kết luận theo danh mục;
gửi kết quả cho B và C.

Không chẩn đoán bệnh từ NDVI. Nếu thiếu căn cứ, ghi "chưa xác định".

``` json
{
  "alert_id": "ALT-001",
  "inspector": "Nguyen Van A",
  "checked_at": "2026-11-07T09:00:00+07:00",
  "conclusion": "OTHER",
  "notes": "Ghi nhận thực tế tại khu vực...",
  "image_path": null,
  "location": null
}
```

## 12. Bàn giao cho Nhóm B

``` text
survey_xxx/
├── metadata.json
├── raw/
├── calibration/
├── gcp/
└── logs/
    ├── survey-log.xlsx
    ├── image_manifest.csv
    └── import-report.json
```

Kèm Survey ID, Plot ID, đường dẫn, số RAW/JPG, trạng thái hiệu chỉnh,
metadata và lỗi đã biết. Nhóm B phải xác nhận nhận và đọc được dữ liệu.

## 13. Checklist nghiệm thu

-   [ ] SOP hoàn thiện.
-   [ ] Model/filter camera được xác nhận.
-   [ ] RAW/JPG đầy đủ.
-   [ ] Ảnh hiệu chỉnh trước/sau có mặt.
-   [ ] Metadata đúng schema.
-   [ ] Script nhập ảnh chạy được.
-   [ ] Manifest/checksum được tạo.
-   [ ] Nhật ký đầy đủ.
-   [ ] Dữ liệu không nằm trong Git.
-   [ ] Lab 4 bắt đầu từ tuần 1.
-   [ ] GCP có dữ liệu nếu điều kiện cho phép.
-   [ ] Có quy trình xác minh cảnh báo.
-   [ ] Nhóm B xác nhận đầu vào.

## 14. Kế hoạch 16 tuần

  Tuần     Công việc                                  Sản phẩm
  -------- ------------------------------------------ -------------------------
  1        Làm quen camera, Lab 1--3, bắt đầu Lab 4   Ảnh thử, nhật ký
  2        Viết SOP, quy trình chụp                   SOP
  3        Metadata tool, importer                    Công cụ
  4        Khảo sát dữ liệu thật                      Survey folder
  5        Hoàn thiện Lab 4, kiểm tra dữ liệu         Báo cáo Lab
  6        GCP và khảo sát định kỳ                    GCP/log
  7        Tiếp tục chuỗi thời gian                   Bộ survey
  8        Kiểm tra cảnh báo đầu tiên                 Field-check
  9--10    Khảo sát định kỳ                           Dữ liệu nhiều thời điểm
  11--12   Xác minh cảnh báo                          Kết quả thực địa
  13       Bàn giao dữ liệu tích hợp                  Dataset
  14       Rà soát dữ liệu                            Báo cáo chất lượng
  15       Hoàn thiện báo cáo                         Báo cáo nhóm
  16       Bàn giao cuối kỳ                           Dataset, SOP, tool

## 15. Git và báo cáo

Branch:

``` text
feature/group-a/metadata-tool
feature/group-a/data-importer
feature/group-a/sop
feature/group-a/gcp
```

Commit:

``` text
feat(acquisition): add metadata generator
feat(acquisition): add image checksum validation
docs(acquisition): add field survey SOP
test(acquisition): validate survey metadata
```

Không commit RAW/JPG/raster lớn hoặc dữ liệu nhạy cảm.

Báo cáo cuối nhóm: thiết bị/cấu hình, SOP, cấu trúc dữ liệu, metadata
tool, kết quả Lab, lỗi thu thập, chất lượng dữ liệu bàn giao, kiểm chứng
thực địa, hạn chế và đề xuất.
