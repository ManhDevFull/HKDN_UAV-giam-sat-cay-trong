# Processing — Nhóm B

Phạm vi tuần 1: đọc dữ liệu RAW Survey3, giữ nguyên dữ liệu nguồn, tách các mặt phẳng Bayer và chuẩn bị bước hiệu chỉnh vignetting. Hiện chưa có ảnh Survey3, nên pipeline có thể chạy bằng mosaic tổng hợp. Đây là nền ban đầu; chưa phải hiệu chỉnh phản xạ bằng tấm chuẩn, demosaic hay pipeline khoa học đã nghiệm thu.

## Cài đặt

Python 3.10 trở lên:

```bash
cd processing
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Đọc file camera cần cài thêm decoder:

```bash
python -m pip install -e '.[raw]'
```

## Chạy với dữ liệu giả

```bash
hkdn-make-sample --output data/synthetic
hkdn-process data/synthetic/mosaic.npy --output output/synthetic-001 --pattern RGGB
```

Kết quả mỗi kênh gồm `.npy` giữ giá trị số và `.png` để xem nhanh; `metadata.json` ghi pattern và kích thước. `data/` và `output/` đã được ignore để tránh đưa dữ liệu vào Git.

## Chạy với RAW

```bash
hkdn-process /duong-dan/anh.CR2 --output output/survey-001 --pattern RGGB
```

`rawpy` đọc sensor mosaic nhìn thấy và metadata cơ bản. Cần xác nhận CFA pattern theo metadata thực tế của Survey3 trước khi xử lý lô ảnh; hiện `RGGB` chỉ là mặc định của fixture. File gốc không bị sửa. Không commit RAW, ảnh trung gian hay kết quả lớn.

## Quy ước đầu vào/đầu ra tạm thời A → B

- Đầu vào: một file RAW gốc bất biến, cùng metadata khảo sát (tên/ID, ngày, camera, thông số chụp và tấm hiệu chỉnh nếu có). Nhóm A cần thống nhất cấu trúc thư mục và `metadata.json` của khảo sát trước khi áp dụng cho dữ liệu thật.
- Đầu ra bước tuần 1: các mặt phẳng Bayer riêng `R`, `G1`, `G2`, `B` dạng `.npy` và PNG xem nhanh, kèm `metadata.json`.
- Việc lưu trữ dữ liệu khảo sát ngoài Git; README chỉ ghi đường dẫn lưu trữ theo quy ước chung.

## Giới hạn hiện tại

Mô-đun vignetting nhận flat field cùng kích thước/kênh và chuẩn hóa theo median, nhưng pipeline mẫu hiện truyền flat toàn số 1 để xác nhận luồng chạy. Tấm hiệu chỉnh thật cần được chụp đúng quy trình và ghép đúng mặt phẳng CFA. Trước khi báo cáo tiêu chí sai số <5%, cần có dữ liệu chuẩn, định nghĩa phép đo và kiểm chứng độc lập. Chưa có orthomosaic hay chỉ số thực vật trong tuần 1.
