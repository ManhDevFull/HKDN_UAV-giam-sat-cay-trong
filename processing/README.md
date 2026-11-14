# Nhóm B — Tuần 2

Nhận `assets/` từ nhóm A: RAW + JPG, có thể kèm `metadata.json`. Bản hiện tại chạy **hiệu chỉnh tương đối bằng phần mềm**, không cần tấm chuẩn.

## Cài và chạy

Python 3.10+, bắt đầu ở gốc repo:

```bash
cd processing
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
process-survey ../assets --mode relative --output output/run-001
```

Windows PowerShell: tạo venv bằng `python -m venv .venv`, kích hoạt bằng `.venv\Scripts\Activate.ps1`. Mỗi lần chạy dùng tên output mới. Không sửa ảnh gốc. Máy bạn cùng nhóm chỉ cần pull code, nhận `assets` riêng rồi chạy các lệnh trên; không cần tải flat-field về.

## Code làm gì?

- **RAW:** giải mã 12-bit, tách Bayer, khử tối góc bằng profile ống kính Survey3W của MAPIR. Dùng thời gian phơi sáng trong JPG ghép cặp để đưa RAW về mốc 0,008 giây ở ISO 100; thiếu EXIF thì ghi rõ bước bị bỏ qua. Không đổi histogram từng ảnh để ép chúng giống nhau.
- **JPG:** ghép cặp theo tên/thời gian/số thứ tự khi không mơ hồ, dùng làm EXIF và preview. JPG đứng riêng chỉ xuất preview, không xuất raster định lượng (đúng mục 4 tài liệu 02).
- **Tham số có trong Git:** `src/processing/profiles/default.json` và `survey3w.json`. Muốn đổi tham số: sửa bản default hoặc dùng `--settings đường/dẫn/settings.json`. Profile chỉ dùng cho Survey3W RAW 4000×3000, giữ nguyên hướng; không trộn RGN/OCN.

**Giới hạn bắt buộc:** thiếu chuẩn phản xạ/ánh sáng nên kết quả là `relative_signal`, chưa phải phần trăm phản xạ. Theo mục 3 tài liệu 02, **chưa được dùng so sánh giữa các lần khảo sát hoặc nghiệm thu sai số phản xạ <5%**. Crosstalk R/G–NIR chưa được khử; RGN không có Red Edge. Metadata và manifest đều ghi các điều kiện này.

## Đầu ra bàn giao nhóm C

Mở `output/run-001/manifest.json`: mỗi mục có `source`, `status`, `preview`, `metadata`; RAW có thêm `raster`, `valid_mask`, `bands`, `units`, `analysis_eligibility`. Đường dẫn tương đối với thư mục output, có thể chuyển nguyên thư mục qua kênh riêng cho nhóm C.

- `bands.tif`: float32 H×W×3, thứ tự **Red, Green, NIR**; Green là trung bình G1/G2. Pixel lỗi là NaN, mặt nạ `valid_mask.tif`: 1 hợp lệ / 0 lỗi. TIFF theo pixel cảm biến, **chưa có tọa độ bản đồ**, chưa phải orthomosaic.
- `R/G1/G2/B.npy`: giữ các mặt phẳng số (B là NIR danh nghĩa với RGN); `preview.png` chỉ để xem. JPG đứng riêng không có TIFF/NPY.
- `summary.json`: số ảnh xử lý, ghép cặp, hiệu chỉnh, lỗi; `quality.flags` đánh dấu ảnh quá tối, `analysis_eligibility` cho biết dữ liệu được phép dùng đến đâu. Nhóm C không coi `relative_corrected` là phản xạ đã kiểm chứng.

`assets/`, dữ liệu tham chiếu tải về, cache, demo và mọi output đều được ignore. Mỗi thư mục output tự có `.gitignore`, kể cả đặt tên khác. **Chỉ commit code, tham số và README.**

Kiểm tra code: `python -m unittest discover -s tests`. Luồng dùng tấm chuẩn vẫn giữ trong `calibration.example.json` nếu sau này có dữ liệu đo thật; chế độ `--mode panel --calibration ...`.

Nguồn: [flat-field MAPIR đã khóa phiên bản](https://github.com/mapircamera/camera-scripts/tree/f127afad0e31370cbb28d1783435cedafd2fd915/Vignette_Correction_Survey3). Sai số nén profile so với flat hãng: P95 ≈ 0,98%, lớn nhất ≈ 3,06%; **không phải sai số phản xạ thực địa**. Chỉ khi muốn tái tạo profile mới chạy `python tools/build_lens_profile.py`; TIFF nguồn tải vào `data/reference/mapir/` và không được commit. Nguồn và giấy phép nằm cùng profile.
