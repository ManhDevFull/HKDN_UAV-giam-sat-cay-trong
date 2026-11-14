# Nhóm B — Tuần 2

Đọc RAW Survey3 → tách Bayer → khử vignetting nếu có flat → hiệu chỉnh phản xạ theo tấm chuẩn → kiểm chứng 3 thời điểm. Chỉ xử lý ảnh, chưa ghép bản đồ hay làm API.

## Cài và chạy

Cần Python 3.10+. Nhận thư mục `assets/` qua kênh riêng, đặt ở gốc repo (không có trong Git).

```bash
cd processing
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
process-survey ../assets --output output/week2-001
```

Windows: dùng `.venv\Scripts\activate` thay lệnh `source`. Survey3 RAW 4000×3000, 18 MB đọc trực tiếp, không cần rawpy. Định dạng camera khác: `python -m pip install -e '.[raw]'`.

Lệnh quét RAW trong các thư mục con; JPG chỉ là ảnh xem trước, không dùng để tính phản xạ. Mỗi lần chạy chọn thư mục output **mới**; ảnh nguồn không bị ghi đè. `assets/`, `data/`, `output/` đã được ignore.

## Khi có tấm chuẩn

```bash
cp calibration.example.json ../assets/calibration.json
```

Sửa file này; lần chạy tiếp theo tự đọc cấu hình:

- Đường dẫn tính từ `assets/`. Mỗi `session` là một thời điểm; sửa `images` thành danh sách tên RAW hoặc glob của buổi đó, `target` là RAW chụp tấm chuẩn. Không đưa target/flat vào `images`.
- `panels`: ít nhất 2 ô chuẩn khác nhau, nên dùng đủ các ô có chứng nhận. Thay `null` bằng phản xạ **theo từng dải từ chứng nhận**, dạng 0–1 (50% = 0.5); không tự dùng số ví dụ.
- `roi = [x, y, rộng, cao]` theo pixel RAW, góc trái trên; tất cả số chẵn, tối thiểu 8×8. Chọn phần trong ô, tránh viền, bóng và vùng cháy sáng. Có thể chạy riêng ảnh target ra output khác để lấy `preview.png`; tọa độ RAW = **2 lần** tọa độ preview, không dùng tọa độ JPG.
- Target và ảnh trong cùng session phải cùng ISO/phơi sáng, ánh sáng ổn định; xác nhận xong mới đổi `exposure_confirmed` thành `true`. Ánh sáng/phơi sáng đổi thì tạo session và chụp chuẩn lại.
- `flat`: RAW/NPY chụp bề mặt sáng đồng đều, không bão hòa, cùng camera/ống kính; thiếu thì để `null` và bước vignetting được bỏ qua có ghi chú. `black_level` chỉ nhập khi đã đo, không biết để `null`.
- `checks`: chọn **cùng vật thể/vùng vật lý** ở 3 thời điểm, giữ cùng `object_id`; mỗi ROI phải ở ảnh cảnh riêng, không dùng ảnh target để tự kiểm chứng.

```bash
process-survey ../assets --output output/week2-002 --require-validation
```

Mỗi kênh đạt khi `100 × (max − min) / mean < 5%` qua 3 thời điểm; đây là độ lặp lại, chưa chứng minh độ chính xác tuyệt đối. Mã thoát: `0` chạy xong; `1` lỗi đầu vào/xử lý; `2` có `--require-validation` nhưng chưa đạt hoặc thiếu kiểm chứng.

## Kết quả và kiểm tra

Trong output: mỗi ảnh có `R/G1/G2/B.npy` (float32), `preview.png`, `metadata.json`; tổng hợp ở `summary.json`. `uncalibrated` là DN; `calibrated` là phản xạ 0–1 theo mô hình tuyến tính. Không chặn giá trị ngoài 0–1 để dễ phát hiện lỗi; pixel bão hòa ghi NaN. G1/G2 là hai vị trí xanh Bayer; với RGN, B là kênh NIR danh nghĩa. Chưa tách chồng phổ R/G với NIR, nên chưa coi đây là hiệu chuẩn phổ đầy đủ của hãng.

Bộ `assets` hiện tại: **22 RAW, 24 JPG; chưa có ảnh chuẩn/flat và số phản xạ chứng nhận**, nên chỉ chạy tiền xử lý, chưa thể nghiệm thu <5%.

Demo hiệu chỉnh có đáp án giả lập (không dùng số này cho ảnh thật):

```bash
make-synthetic-survey --week2 --output data/demo-week2
process-survey data/demo-week2 --output output/demo-week2 --require-validation
python -m unittest discover -s tests
```

Tham khảo: [giải mã RAW của MAPIR](https://github.com/mapircamera/camera-scripts/blob/main/Convert_Survey3_RAW_To_Tiff/Convert_Survey3_RAW_to_Tiff.py), [hiệu chỉnh phản xạ](https://www.mapir.camera/pages/what-is-reflectance-calibration), [chồng phổ RGN](https://www.mapir.camera/en-gb/pages/how-do-you-capture-3-channels-bands-of-separate-multispectral-reflectance-data-in-a-traditional-rgb-color-camera).
