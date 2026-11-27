# DANH SÁCH CÔNG VIỆC CHI TIẾT NHÓM B — XỬ LÝ ẢNH & PHÂN TÍCH ĐA PHỔ (AGRISCAN)

> Tài liệu này tổng hợp đầy đủ yêu cầu từ bộ tài liệu gốc (`00-BAT-DAU-TAI-DAY.md` đến `05-Phan-cong-nhom-6.md`) và đặc tả kỹ thuật (`Nhom_B_Xu_ly_anh_va_phan_tich.md`), sắp xếp theo đúng thứ tự thực hiện từ đầu đến khi bàn giao cuối kỳ, kèm hướng dẫn **cách làm chi tiết** cho từng bước.

---

## I. NGUYÊN TẮC CỐT LÕI & RANH GIỚI KỸ THUẬT (PHẢI THUỘC LÒNG)

1. **Sàng lọc, KHÔNG chẩn đoán (`00`, `01`)**:
   - Hệ thống chỉ khoanh vùng **"cây/vùng có dấu hiệu bất thường trên tán lá, cần đi kiểm tra"** và xếp hạng ưu tiên, tuyệt đối không kết luận *"cây bị bệnh X"*.
   - **Không huấn luyện AI / Học máy có giám sát**: Phát hiện bất thường bằng phương pháp thống kê và không giám sát (Ngưỡng tuyệt đối, Dị thường không gian Z-score/IQR/Percentile, Dị thường thời gian). Chấp nhận báo động giả theo nguyên tắc *"thà báo dư còn hơn bỏ sót"*.
2. **Ràng buộc thiết bị thực tế — MAPIR Survey3W bản RGN (`02`)**:
   - Cảm biến Sony Exmor R IMX117 12MP (`4000 × 3000`), chụp cầm tay / gắn sào (độ cao ~3m, GSD ≈ `0.14 cm/pixel`) / giá cố định. **Tuyệt đối không bay drone.**
   - Bộ lọc thực tế là **RGN**: **Red (660 nm)**, **Green (550 nm)**, **NIR (850 nm)**.
   - **Chỉ tính các chỉ số có kênh tương ứng**: Tính được **NDVI, GNDVI, SAVI**. **KHÔNG tính NDRE** (vì bản RGN không có kênh Red-Edge ~730nm). Không trộn lẫn dữ liệu giữa máy RGN và OCN.
   - **Dùng ảnh RAW 12-bit, không dùng JPG để phân tích định lượng**: File `.RAW` của Survey3W là dữ liệu nhị phân 12-bit (`0..4095`), còn `.JPG` chỉ là ảnh 8-bit đã nén dùng để xem nhanh và đọc EXIF/GPS.
3. **Tách rời tầng thu thập (M1) và tầng xử lý (M2–M5) (`03`)**:
   - Nhóm B chỉ nhận dữ liệu qua **Hợp đồng dữ liệu A → B** (thư mục khảo sát chuẩn + `metadata.json`). Không trộn logic phần cứng chụp vào pipeline xử lý để sau này chuyển từ sào sang drone chỉ cần thay `acquisition_method: "drone"`.
   - **Dữ liệu gốc là bất biến**: Không bao giờ ghi đè hay chỉnh sửa file trong `raw/` hoặc `assets/`. Mọi kết quả trung gian và đầu ra phải ghi sang thư mục mới.

---

## II. PHÂN CÔNG TRONG NHÓM B (2 THÀNH VIÊN) & CÁC MỐC NGHIỆM THU

| Thành viên | Phụ trách | Mô-đun theo đặc tả `03` | Công việc chính |
| :--- | :--- | :--- | :--- |
| **B1** | Tiền xử lý, Hiệu chỉnh bức xạ & Ghép ảnh | **M2** (`M2.1`–`M2.6`) & **M3** (`M3.1`–`M3.5`) | Đọc RAW 12-bit, tách kênh R-G-NIR, khử tối góc (vignetting), quy đổi phản xạ bằng tấm chuẩn (sai số < 5%), kiểm tra chất lượng ảnh, ghép ảnh Orthomosaic có tọa độ. |
| **B2** | Chỉ số thực vật, Phát hiện bất thường & Xuất kết quả | **M4** (`M4.1`–`M4.7`) & **M5** (`M5.1`–`M5.8`) | Tính NDVI/GNDVI/SAVI, tách nền đất trống, chia ô lưới phân tích (Unit), thống kê theo vùng, phát hiện bất thường (A/B/C), gom cụm, xếp hạng ưu tiên và xuất dữ liệu cho Nhóm C. |
| **B1 + B2** | Tích hợp & Kiểm chứng | Pipeline, CLI, Unit Test, Báo cáo Lab 2 & Lab 4 | Ghép pipeline chạy 1 lệnh duy nhất, viết `pytest`, phân tích chuỗi thời gian Lab 4 và tinh chỉnh ngưỡng cảnh báo sau khi Nhóm A đi kiểm tra thực địa. |

### 4 Mốc nghiệm thu bắt buộc của Nhóm B (`04-Ke-hoach-16-tuan.md`):
- **🚩 Mốc G1 (Cuối tuần 3)**: Đọc RAW, khử vignetting, hiệu chỉnh phản xạ bằng tấm chuẩn. **Tiêu chí đạt**: Cùng một vật thể chụp ở **3 thời điểm (Sáng / Trưa / Chiều)**, sau hiệu chỉnh giá trị phản xạ chênh lệch **< 5%**.
- **🚩 Mốc G2 (Cuối tuần 8)**: Ghép thành công **≥ 90% số ảnh** thành Orthomosaic không thủng lỗ vùng mục tiêu; chạy pipeline **1 lệnh duy nhất** từ thư mục ảnh thô $\rightarrow$ bản đồ NDVI + danh sách cảnh báo (Phương pháp A + B) có xếp hạng.
- **🚩 Mốc G3 (Cuối tuần 13)**: Bổ sung phát hiện dị thường theo thời gian (Phương pháp C) trên tối thiểu 2 đợt khảo sát; tích hợp đầu-cuối với Backend/Web của Nhóm C và tinh chỉnh ngưỡng theo kết quả kiểm tra thực địa của Nhóm A.
- **🚩 Mốc G4 (Cuối tuần 16)**: Hoàn thiện bộ test tự động, tài liệu kỹ thuật từng mô-đun, báo cáo kiểm chứng hiệu chỉnh (< 5%) và báo cáo phân tích chuỗi thời gian Lab 4.

---

## III. TRẠNG THÁI HIỆN TẠI & DANH SÁCH CÔNG VIỆC THEO THỨ TỰ (1 → 12)

---

### CÔNG VIỆC 1: Chuẩn hóa cấu trúc dự án, Môi trường & Quản lý cấu hình YAML
- **Trạng thái**: ✅ **ĐÃ HOÀN THÀNH**
- **Mục tiêu**: Thiết lập cấu trúc `src/agriscan/` theo chuẩn mô-đun và tách toàn bộ tham số khỏi code vào các file YAML có đánh phiên bản (đảm bảo yêu cầu phi chức năng về **Khả năng tái lập** trong `03-Yeu-cau-tinh-nang.md`).
- **File thực hiện**:
  - Cấu hình: `processing/configs/default.yaml`, `camera.yaml`, `calibration.yaml`, `indices.yaml`, `anomaly.yaml`.
  - Code: `processing/src/agriscan/pipeline/steps.py` (`load_config`, `load_all_configs`), `processing/pyproject.toml`, `.gitignore`.
- **Cách làm**:
  1. Định nghĩa cấu hình thiết bị trong `camera.yaml` (`MAPIR Survey3W`, filter `RGN`, kích thước `4000×3000`, `12-bit`, `cfa_pattern: RGGB`, bước sóng `red: 660`, `green: 550`, `nir: 850`).
  2. Tách các ngưỡng chỉ số (`indices.yaml`) và ngưỡng cảnh báo (`anomaly.yaml`) thành tham số đọc qua `PyYAML`, không hard-code trong hàm tính toán.
  3. Chặn toàn bộ dữ liệu ảnh lớn (`assets/`, `data/`, `output/`, `*.RAW`, `*.JPG`, `*.tif`, `*.npy`) trong `.gitignore`.

---

### CÔNG VIỆC 2: Kiểm tra Hợp đồng dữ liệu đầu vào A → B (`M1` → `M2`)
- **Trạng thái**: ✅ **ĐÃ HOÀN THÀNH**
- **Mục tiêu**: Đọc `metadata.json` và tự động kiểm tra tính toàn vẹn của thư mục khảo sát trước khi đưa vào pipeline xử lý.
- **File thực hiện**:
  - `processing/src/agriscan/io/metadata_reader.py`
  - `processing/src/agriscan/io/image_validator.py`
- **Cách làm**:
  1. **Trong `metadata_reader.py`**:
     - Đọc file `metadata.json`, kiểm tra các trường bắt buộc theo hợp đồng mục 2 của `03-Yeu-cau-tinh-nang.md`: `survey_id`, `plot_id`, `datetime_start <= datetime_end` (chuẩn ISO 8601), `acquisition_method` (`handheld` | `pole` | `fixed` | `drone`), `camera.model`, `camera.filter` (`RGN`), `camera.bands` (`red: 660, green: 550, nir: 850`), `height_m`, `gsd_cm`, `overlap`, `calibration_target`, `image_count`.
     - Hỗ trợ thêm `"drone"` vào tập `VALID_ACQUISITION_METHODS` để sẵn sàng mở rộng khi có drone.
  2. **Trong `image_validator.py`**:
     - Kiểm tra sự tồn tại của thư mục `raw/`, `metadata.json` và hai file ảnh tấm chuẩn `calibration_target.before` / `calibration_target.after`.
     - Quét toàn bộ file `.RAW` và `.JPG`: kiểm tra kích thước file `.RAW` phải đúng `18,000,000 bytes` (`4000 × 3000 × 12-bit`), kiểm tra mã băm SHA-256 phát hiện file hỏng/trùng, đối chiếu số lượng cặp `.RAW`/`.JPG` và đọc EXIF/GPS từ file `.JPG` đi kèm.
     - Phân loại rõ **`errors`** (lỗi nghiêm trọng bắt buộc dừng pipeline: thiếu thư mục `raw/`, không có ảnh `.RAW`, file `.RAW` hỏng) và **`warnings`** (cảnh báo cần xem xét `needs_review`: thiếu ảnh tấm chuẩn, số lượng RAW/JPG lệch nhau).
- **Cách chạy kiểm tra**:
  ```powershell
  python -m agriscan.cli validate ..\assets
  ```

---

### CÔNG VIỆC 3: Giải mã file `.RAW` 12-bit thực tế của MAPIR Survey3W (`M2.1` — Phần 1)
- **Trạng thái**: ✅ **ĐÃ HOÀN THÀNH**
- **Mục tiêu**: Giải mã chính xác dữ liệu cảm biến Bayer 12-bit từ file `.RAW` gốc của camera MAPIR Survey3W mà không làm biến đổi giá trị bức xạ.
- **File thực hiện**:
  - `processing/src/agriscan/calibration/decoder.py`
  - `processing/src/agriscan/io/raw_reader.py`
- **Cách làm**:
  1. File `.RAW` của MAPIR Survey3W là định dạng **12-bit little-endian packed headerless** (không có header TIFF/EXIF nên `rawpy` mặc định không đọc được trực tiếp).
  2. Đọc mảng byte `uint8` có kích thước `18,000,000 bytes`, gom theo từng cụm 3 byte `(b0, b1, b2)` và giải nén bằng phép dịch bit sang 2 điểm ảnh 12-bit liên tiếp (`uint16`, giá trị `0..4095`):
     $$\text{pixel}_0 = b_0 \mid ((b_1 \ \& \ \text{0x0F}) \ll 8)$$
     $$\text{pixel}_1 = (b_1 \gg 4) \mid (b_2 \ll 4)$$
  3. Reshape mảng về kích thước `(3000, 4000)` kiểu `uint16`.
  4. Tính thống kê kiểm tra điểm ảnh (`min`, `max`, `mean`, `std`, số pixel bằng `0`, số pixel bão hòa `== 4095`) và gắn thông tin camera/filter từ `metadata.json`.
- **Cách chạy kiểm tra**:
  ```powershell
  python -m agriscan.cli read-raw ..\assets\raw\2026_1102_041147_001.RAW --metadata ..\assets\metadata.json
  ```

---

### CÔNG VIỆC 4: Tách 3 kênh phổ Red (660nm), Green (550nm), NIR (850nm) (`M2.1` — Phần 2)
- **Trạng thái**: ✅ **ĐÃ HOÀN THÀNH (Người phụ trách: B1)**
- **Mục tiêu**: Từ mảng Bayer mosaic `(3000, 4000)` đã giải mã ở Công việc 3, tách thành 3 kênh phổ vật lý tương ứng với bộ lọc **RGN** của camera MAPIR Survey3W.
- **File thực hiện**:
  - `processing/src/agriscan/calibration/band_extractor.py`
- **Cách làm chi tiết**:
  1. **Ánh xạ vị trí lưới Bayer `RGGB` sang kênh phổ `RGN`**:
     Trên cảm biến Bayer 2×2 của MAPIR Survey3W RGN (đã kiểm chứng tương quan với ảnh JPG gốc):
     - Vị trí `[0::2, 0::2]` (ô **R** trên Bayer) $\rightarrow$ Kênh **Red (660 nm)**, kích thước `1500 × 2000`.
     - Vị trí `[0::2, 1::2]` (ô **G1**) và `[1::2, 0::2]` (ô **G2**) $\rightarrow$ Kênh **Green (550 nm)**:
       - *Cách 1 (Giữ độ phân giải gốc của mặt phẳng Bayer `1500 × 2000`)*: Lấy trung bình cộng hai mặt phẳng lấy mẫu xanh lá:
         $$\text{Green} = \frac{G_1.astype(\text{float32}) + G_2.astype(\text{float32})}{2.0}$$
       - *Cách 2 (Nội suy Demosaic cùng kích thước `3000 × 4000` khi cần ghép ảnh)*: Dùng nội suy song tuyến tính (bilinear demosaicing) trên từng kênh để đưa cả 3 kênh `Red`, `Green`, `NIR` về cùng kích thước `(3000, 4000)` hoặc giữ `(1500, 2000)` đồng nhất cho cả 3 kênh (cần cho phép chọn qua tham số cấu hình `keep_half_resolution: true/false` trong `camera.yaml`).
     - Vị trí `[1::2, 1::2]` (ô **B** trên Bayer) $\rightarrow$ Kênh **NIR (850 nm)**, kích thước `1500 × 2000`.
  2. **Viết hàm `extract_rgn_bands(mosaic: np.ndarray, camera_config: dict) -> dict[str, np.ndarray]`**:
     - Kiểm tra `mosaic` là mảng 2D có kích thước chẵn.
     - Trả về dictionary `{"red": red_band, "green": green_band, "nir": nir_band}` cùng metadata bước sóng (`660`, `550`, `850`).
  3. **Viết hàm `save_extracted_bands(bands: dict[str, np.ndarray], output_dir: Path)`**:
     - Xuất từng kênh ra thư mục trung gian `data/intermediate/<image_name>/` dưới dạng `red.tif`, `green.tif`, `nir.tif` (sử dụng `rasterio` hoặc `tifffile`/`PIL`).
- **Tiêu chí kiểm thử**:
  - 3 mảng `red`, `green`, `nir` phải có cùng `shape` (`(1500, 2000)` hoặc `(3000, 4000)`), kiểu `float32` hoặc `uint16`, không chứa `NaN`.

---

### CÔNG VIỆC 5: Khử tối góc (Vignetting) & Kiểm tra chất lượng bức xạ (`M2.2`, `M2.5`)
- **Trạng thái**: ⏳ **CẦN LÀM (Người phụ trách: B1 — đã có công thức cơ bản trong `src/processing/vignetting.py`)**
- **Mục tiêu**: Khắc phục hiện tượng suy giảm độ sáng ở rìa ống kính góc rộng (Survey3W 87° HFOV) và tự động phát hiện ảnh quá sáng/quá tối/lệch sáng trước khi tính phản xạ.
- **File cần tạo**:
  - `processing/src/agriscan/calibration/vignetting.py`
  - `processing/src/agriscan/calibration/quality_check.py`
- **Cách làm chi tiết**:
  1. **Trong `calibration/vignetting.py` (`M2.2`)**:
     - Chuyển và nâng cấp hàm `correct_vignetting(band: np.ndarray, flat_field: np.ndarray | None, dark_level: float = 0.0)` từ `src/processing/vignetting.py`:
       - Trừ mức đen cảm biến (`dark_level`, nếu có): $I_0 = \max(I - \text{dark\_level}, 0)$.
       - Nếu có ảnh chụp mặt phẳng trắng đồng nhất (Flat-field) cho từng kênh (`flat_red`, `flat_green`, `flat_nir`): chuẩn hóa `flat_field` theo giá trị trung vị (`median`) ở vùng tâm rồi chia:
         $$I_{\text{corr}} = \frac{I_0}{\max(F / \text{median}(F), \epsilon)}$$
       - Nếu chưa có ảnh Flat-field thực nghiệm: hỗ trợ chế độ ước lượng mặt phẳng polynomial / radial bậc 2 từ cấu hình `calibration.yaml` (và ghi rõ trong báo cáo là `"vignetting_method": "radial_model"` hoặc `"flat_field"`).
  2. **Trong `calibration/quality_check.py` (`M2.5`)**:
     - Viết hàm `check_radiometric_quality(bands, before_target_stats=None, after_target_stats=None)`:
       - **Cảnh báo quá sáng (Overexposed)**: Nếu tỷ lệ pixel chạm ngưỡng bão hòa (`>= 4090` trên thang 12-bit `4095`) vượt quá `1%` diện tích ảnh (hoặc vượt quá `0.1%` trên vùng tấm hiệu chỉnh).
       - **Cảnh báo quá tối (Underexposed)**: Nếu giá trị trung bình kênh `< 5%` thang đo (`< 200` trên thang `4095`).
       - **Cảnh báo thiếu ảnh tấm chuẩn**: Nếu không tìm thấy `target_before` hoặc `target_after`.
       - **Cảnh báo thay đổi ánh sáng giữa chuyến khảo sát**: So sánh giá trị trung bình của tấm chuẩn chụp trước (`target_before`) và chụp sau (`target_after`). Nếu chênh lệch `> 15%`, gắn cờ cảnh báo `"illumination_drift_warning"` vì mây che hoặc nắng thay đổi mạnh trong lúc chụp.

---

### CÔNG VIỆC 6: Hiệu chỉnh phản xạ bằng tấm chuẩn & Kiểm chứng Mốc G1 < 5% (`M2.3`, `M2.4`, `M2.6`)
- **Trạng thái**: ⏳ **CẦN LÀM — QUAN TRỌNG NHẤT GIAI ĐOẠN I (Người phụ trách: B1)**
- **Mục tiêu**: Quy đổi giá trị số thô của cảm biến (DN: `0..4095`) sang **giá trị phản xạ bề mặt thực tế (Reflectance: `0.0..1.0`, kiểu `float32`)** bằng ảnh tấm hiệu chỉnh `MAPIR T4P-R25`, và đạt tiêu chí nghiệm thu **Mốc G1 (sai lệch < 5% ở 3 thời điểm trong ngày)**.
- **File cần tạo**:
  - `processing/src/agriscan/calibration/reflectance.py`
- **Cách làm chi tiết**:
  1. **Trích xuất giá trị số trung bình trên tấm hiệu chỉnh (`extract_target_dn`)**:
     - التấm hiệu chỉnh **MAPIR T4P-R25** gồm 4 ô phản xạ chuẩn đã được đo trong phòng thí nghiệm (đen ~2%, xám đậm ~21%, xám nhạt ~44%, trắng ~85% — lấy giá trị phản xạ chuẩn xác theo bảng thông số đi kèm tấm T4P-R25 cho từng bước sóng `660nm`, `550nm`, `850nm` và khai báo trong `configs/calibration.yaml`).
     - Hỗ trợ 2 chế độ lấy vùng ROI của các ô trên ảnh `target_before.RAW` và `target_after.RAW`:
       - *Tự động / Bán tự động*: Đọc tọa độ bounding box `(x, y, w, h)` của từng ô màu từ file cấu hình/JSON hoặc phát hiện vùng ô vuông trên tấm chuẩn.
       - Lấy giá trị **trung vị (`median`) hoặc trung bình cắt biên (trimmed mean)** ở vùng lõi của mỗi ô (bỏ 20% rìa ô để tránh hiệu ứng lóa biên) cho từng kênh `Red`, `Green`, `NIR`.
  2. **Tính hàm quy đổi Empirical Line Method (ELM) theo từng kênh phổ**:
     - Với mỗi kênh $c \in \{\text{red}, \text{green}, \text{nir}\}$:
       - Nếu dùng nhiều ô trên tấm T4P-R25 (Empirical Line 2–4 điểm): Hồi quy tuyến tính bậc nhất giữa giá trị số cảm biến $\text{DN}_c$ và hệ số phản xạ chuẩn $R_{\text{known}, c}$:
         $$R_c(x, y) = a_c \cdot \text{DN}_c(x, y) + b_c$$
       - Nếu dùng 1 ô chuẩn có hệ số phản xạ $R_{\text{ref}, c}$ (One-point calibration có trừ mức đen $\text{DN}_{\text{dark}, c}$):
         $$R_c(x, y) = \frac{\text{DN}_c(x, y) - \text{DN}_{\text{dark}, c}}{\text{DN}_{\text{target}, c} - \text{DN}_{\text{dark}, c}} \times R_{\text{ref}, c}$$
       - Nếu có cả `target_before` (thời điểm $t_{\text{start}}$) và `target_after` (thời điểm $t_{\text{end}}$): Nội suy tuyến tính hệ số $(a_c, b_c)$ theo thời gian chụp $t_i$ của từng bức ảnh khảo sát (lấy từ EXIF `DateTimeOriginal`), hoặc lấy trung bình cộng hệ số trước và sau.
     - Giới hạn (clip) giá trị phản xạ hợp lệ trong khoảng `[0.0, 1.0]` (hoặc giữ giá trị `NaN` cho pixel `NoData`), kiểu dữ liệu **`float32`**.
  3. **Hiệu chỉnh nhiễu chéo (Crosstalk) tùy chọn (`M2.6` — Ưu tiên C)**:
     - Cho phép nhân ma trận hiệu chỉnh 3×3 giữa `[Red, Green, NIR]` nếu có ma trận hệ số crosstalk từ MAPIR Camera Control trong `calibration.yaml`.
  4. **Hàm kiểm chứng Mốc G1 (`verify_calibration_stability`)**:
     - Nhận dữ liệu phản xạ của cùng một vật thể kiểm tra (ví dụ một ô màu hoặc tấm bìa chuẩn không đổi) chụp ở **3 thời điểm: Sáng ($R_1$), Trưa ($R_2$), Chiều ($R_3$)**.
     - Tính độ lệch tương đối lớn nhất giữa các thời điểm so với giá trị trung bình / tham chiếu:
       $$D(\%) = \frac{|R_i - R_{\text{ref}}|}{R_{\text{ref}}} \times 100\%$$
     - Xuất bảng báo cáo JSON/CSV kiểm chứng: Đạt Mốc G1 khi $D(\%) < 5\%$ trên cả kênh Red và NIR.

---

### CÔNG VIỆC 7: Đọc/Ghi GeoTIFF chuẩn GIS & Ghép ảnh Orthomosaic (`M2.4`, `M3.1`–`M3.5`)
- **Trạng thái**: ⏳ **CẦN LÀM (Người phụ trách: B1)**
- **Mục tiêu**: Xuất ảnh phản xạ đa băng dạng GeoTIFF (`float32`, giá trị `0..1`), gắn tọa độ EXIF GPS / GCP và ghép nhiều ảnh chụp theo lưới thành một bản đồ trực giao duy nhất (`orthomosaic.tif`) kèm báo cáo chất lượng ghép (`mosaic-quality.json`).
- **File cần tạo**:
  - `processing/src/agriscan/io/raster_io.py`
  - `processing/src/agriscan/mosaicking/georeference.py`
  - `processing/src/agriscan/mosaicking/odm_runner.py`
  - `processing/src/agriscan/mosaicking/mosaic_quality.py`
- **Cách làm chi tiết**:
  1. **Trong `io/raster_io.py` (`M2.4`)**:
     - Viết hàm `write_geotiff(path, data, crs, transform, nodata=np.nan, band_names=None)` và `read_geotiff(path)` bằng `rasterio`.
     - Hỗ trợ ghi cả GeoTIFF 1 băng (cho `ndvi.tif`, `vegetation-mask.tif`) và GeoTIFF 3 băng (`Red`, `Green`, `NIR`, kiểu `float32`, giá trị `0..1`, `nodata = np.nan` hoặc `-9999.0`) cho ảnh phản xạ và `orthomosaic.tif`.
  2. **Trong `mosaicking/georeference.py` (`M3.2`, `M3.3`)**:
     - Đọc tọa độ GPS (`GPSLatitude`, `GPSLongitude`, `GPSAltitude`) từ EXIF của file `.JPG` tương ứng với mỗi file `.RAW` (hoặc tạo bảng tọa độ tâm ảnh).
     - Nếu có file điểm khống chế mặt đất `gcp/gcp_points.csv` (`M3.3`): đọc danh sách điểm GCP (`gcp_id, x, y, z, crs, pixel_x, pixel_y`) và chuyển về định dạng `gcp_list.txt` chuẩn của OpenDroneMap hoặc dùng `rasterio.transform.from_gcps()` để nắn chỉnh hình học.
     - Nếu chụp trên luống cây nhỏ bằng sào mà GPS kèm máy sai số 4–7m: hỗ trợ chế độ tạo hệ tọa độ lưới cục bộ (Local Metric Grid theo mét dựa trên độ cao chụp `height_m: 3.0`, `gsd_cm: 0.14` và `overlap: 0.80/0.75`) rồi neo vào tọa độ GPS gốc của góc vườn (`plot-A`).
  3. **Trong `mosaicking/odm_runner.py` (`M3.1`, `M3.5`)**:
     - Cung cấp 2 chế độ ghép ảnh:
       - **Chế độ A (Tích hợp OpenDroneMap — ODM)**: Chuẩn bị thư mục ảnh TIFF 16-bit/float32 đã gắn thẻ EXIF GPS, gọi lệnh ODM qua Docker/CLI (`docker run ... opendronemap/odm --radiometric-calibration none --fast-orthophoto`), thu thập `odm_orthophoto.tif` và `odm-log.txt`.
       - **Chế độ B (Ghép ảnh 2D Feature-based / Grid Stitching bằng OpenCV + Rasterio)**: Rất hữu ích khi chạy trực tiếp trên máy tính không cài Docker hoặc với bộ ảnh chụp bằng sào ở độ cao 3m. Dùng thuật toán SIFT/ORB tìm điểm đặc trưng trên kênh Green/NIR giữa các ảnh liền kề, ước lượng ma trận biến đổi Affine/Homography (áp dụng cùng một ma trận hình học cho cả 3 kênh Red, Green, NIR để bảo đảm 3 kênh **đồng đăng ký tuyệt đối** đến từng pixel), sau đó ghép (blend) thành `orthomosaic.tif` có gắn `CRS` (ví dụ `EPSG:4326` hoặc `EPSG:32648` cho Tây Nguyên/Việt Nam) và `Affine transform`.
  4. **Trong `mosaicking/mosaic_quality.py` (`M3.4`)**:
     - Kiểm tra và xuất file `processed/mosaic/mosaic-quality.json`:
       - `input_images`: Tổng số ảnh đầu vào.
       - `aligned_images`: Số ảnh ghép thành công và tỷ lệ `%` (tiêu chí nghiệm thu M3: **≥ 90%**).
       - `failed_images`: Danh sách tên các ảnh không ghép được.
       - `valid_coverage_ratio` & `has_internal_holes`: Kiểm tra trong vùng mục tiêu có bị thủng lỗ (`NoData` nằm lọt giữa vùng ảnh) hay không.
       - `crs`, `resolution_m`, `bounds`.

---

### CÔNG VIỆC 8: Tính các chỉ số thực vật NDVI, GNDVI, SAVI (`M4.1`, `M4.2`, `M4.6`)
- **Trạng thái**: ⏳ **CẦN LÀM (Người phụ trách: B2)**
- **Mục tiêu**: Tính toán chính xác các chỉ số thực vật từ ảnh phản xạ / Orthomosaic đã hiệu chỉnh, xử lý an toàn các điểm `NoData` và mẫu số bằng `0`, đồng thời xuất ảnh màu trực quan kèm thang chú giải.
- **File cần tạo**:
  - `processing/src/agriscan/indices/ndvi.py`
  - `processing/src/agriscan/indices/gndvi.py`
  - `processing/src/agriscan/indices/savi.py`
- **Cách làm chi tiết**:
  1. **Kiểm tra điều kiện đầu vào**:
     - Hai mảng kênh phổ (`red`, `nir` hoặc `green`, `nir`) phải có cùng `shape`, cùng `CRS` và `transform`.
     - Chuyển kiểu sang `np.float32`.
  2. **Công thức tính trong `indices/ndvi.py` (`M4.1` — Bắt buộc)**:
     $$\text{NDVI} = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red}}$$
     - Khởi tạo mảng kết quả bằng `np.nan` (`dtype=np.float32`).
     - Chỉ tính tại các pixel hợp lệ: `valid = np.isfinite(red) & np.isfinite(nir) & (red >= 0) & (nir >= 0) & ((nir + red) > 1e-6)`.
     - Giới hạn giá trị hợp lệ trong `[-1.0, 1.0]`.
  3. **Công thức tính trong `indices/gndvi.py` & `indices/savi.py` (`M4.2` — Nên có)**:
     - **GNDVI** (nhạy với hàm lượng diệp lục):
       $$\text{GNDVI} = \frac{\text{NIR} - \text{Green}}{\text{NIR} + \text{Green}}$$
     - **SAVI** (hiệu chỉnh ảnh hưởng của nền đất trống khi cây còn nhỏ/thưa, hệ số $L = 0.5$ đọc từ `configs/indices.yaml`):
       $$\text{SAVI} = \frac{\text{NIR} - \text{Red}}{\text{NIR} + \text{Red} + L} \times (1 + L)$$
  4. **Xuất ảnh bản đồ màu trực quan `ndvi-color-preview.png` (`M4.6` — Bắt buộc)**:
     - Dùng `matplotlib` với bảng màu chuẩn nông nghiệp `RdYlGn` (Đỏ: `< 0.2` đất trống/cây suy kiệt $\rightarrow$ Vàng: `0.3 – 0.5` cây đang stress $\rightarrow$ Xanh lá đậm: `0.6 – 0.9` thực vật khỏe mạnh), vẽ kèm thanh chú giải (colorbar) từ `-0.2` đến `1.0` để phục vụ báo cáo và xem nhanh.

---

### CÔNG VIỆC 9: Tách nền đất trống (Masking), Chia ô phân tích (Unit) & Thống kê (`M4.3`, `M4.4`, `M4.5`)
- **Trạng thái**: ⏳ **CẦN LÀM (Người phụ trách: B2)**
- **Mục tiêu**: Loại bỏ pixel đất trống/bóng râm/vật nhân tạo để không làm sai lệch chỉ số sức khỏe của cây (`M4.3`), chia vườn thành các đơn vị phân tích cố định (`unit-A001`, `unit-A002`...) và tính thống kê chi tiết cho từng ô.
- **File cần tạo**:
  - `processing/src/agriscan/indices/masking.py`
  - `processing/src/agriscan/indices/statistics.py`
- **Cách làm chi tiết**:
  1. **Tách nền thực vật trong `indices/masking.py` (`M4.3`)**:
     - Đọc ngưỡng `vegetation_ndvi_min` từ `configs/indices.yaml` (mặc định thử nghiệm `0.2`, có thể tinh chỉnh thực nghiệm).
     - Tạo mặt nạ nhị phân `vegetation_mask` (`uint8`):
       - `1`: Pixel thực vật hợp lệ (`np.isfinite(ndvi) & (ndvi >= threshold)`).
       - `0`: Đất trống, bóng râm, đường đi, mái tôn hoặc `NoData`.
     - Xuất file `processed/indices/vegetation-mask.tif` giữ nguyên `CRS` và `transform`.
  2. **Chia đơn vị phân tích (Analysis Units) trong `indices/masking.py` (`M4.4`)**:
     - Viết hàm `generate_analysis_units(raster_shape, transform, crs, grid_rows, grid_cols, plot_prefix="A")`:
       - Chia vùng khảo sát thành lưới các ô chữ nhật cố định (hoặc đọc từ file ranh giới `units.geojson` nếu đã có).
       - Gán mã định danh cố định, nhất quán qua các đợt khảo sát: `unit-A001`, `unit-A002`, ..., `unit-A0NN` (theo thứ tự hàng-cột cố định để đợt khảo sát sau so sánh đúng vị trí của đợt trước).
       - Với mỗi unit, tạo `shapely.geometry.Polygon` theo tọa độ địa lý (`CRS`), tọa độ tâm (`center_point`) và diện tích (`area_m2`).
  3. **Tính thống kê vùng trong `indices/statistics.py` (`M4.5`)**:
     - Với mỗi `unit_id`, **chỉ lấy các pixel thuộc vùng thực vật** (`vegetation_mask == 1`) bên trong ô đó để tính:
       - `mean_value` (trung bình)
       - `median_value` (trung vị)
       - `std_value` (độ lệch chuẩn)
       - `min_value`, `max_value`
       - `p10_value`, `p25_value`, `p75_value`, `p90_value` (các phân vị)
       - `pixel_count` (số pixel thực vật hợp lệ) và `vegetation_coverage_ratio` (tỷ lệ độ phủ tán lá trong ô).
     - Nếu một ô có quá ít pixel thực vật (ví dụ `pixel_count < min_valid_pixels` do toàn đất trống), đánh dấu `is_valid_unit: false` để không báo động nhầm đất trống là cây bệnh.
     - Xuất kết quả ra `processed/indices/statistics.csv` và `processed/indices/statistics.json`.

---

### CÔNG VIỆC 10: Phát hiện bất thường (Phương pháp A, B, C), Gom cụm & Xếp hạng ưu tiên (`M5.1`–`M5.8`)
- **Trạng thái**: ⏳ **CẦN LÀM — MÔ-ĐUN LÕI CỦA SẢN PHẨM (Người phụ trách: B2)**
- **Mục tiêu**: Phát hiện sớm các ô/vùng cây trồng bị stress bằng 3 phương pháp thống kê không giám sát, gom cụm và xếp hạng mức độ ưu tiên để chuyên gia đi kiểm tra thực địa.
- **File cần tạo**:
  - `processing/src/agriscan/anomalies/absolute.py`
  - `processing/src/agriscan/anomalies/spatial.py`
  - `processing/src/agriscan/anomalies/temporal.py`
  - `processing/src/agriscan/anomalies/clustering.py`
  - `processing/src/agriscan/anomalies/ranking.py`
- **Cách làm chi tiết**:
  1. **Phương pháp A — Ngưỡng tuyệt đối (`anomalies/absolute.py` — `M5.1`)**:
     - Đọc ngưỡng `ndvi_min` từ `configs/anomaly.yaml` (ví dụ `0.35` hoặc `0.40` tùy loại cây).
     - Mọi unit hợp lệ có `mean_ndvi < ndvi_min` được đánh dấu là candidate alert với `anomaly_type = "absolute"`, `reference_value = ndvi_min`, `reason = f"Mean NDVI ({obs:.2f}) is below absolute threshold ({ndvi_min:.2f})"`.
  2. **Phương pháp B — Dị thường không gian (`anomalies/spatial.py` — `M5.2`)**:
     - So sánh từng unit với mặt bằng chung của toàn bộ các unit hợp lệ trong cùng đợt khảo sát.
     - Hỗ trợ cả **Z-score** và **IQR / Robust Z-score** (để chống nhiễu khi vườn có phân bố lệch):
       $$z_i = \frac{x_i - \mu}{\sigma}$$
     - Xử lý an toàn trường hợp $\sigma = 0$ (khi mọi ô bằng nhau thì không sinh cảnh báo).
     - Nếu $z_i < -z_{\text{threshold}}$ (ví dụ $z_i < -1.5$, tức thấp hơn mặt bằng chung của vườn quá 1.5 độ lệch chuẩn): tạo cảnh báo `anomaly_type = "spatial"`, `reference_value = round(mu, 4)`, `reason = f"Spatial anomaly: NDVI ({x_i:.2f}) is {abs(z_i):.2f} std below plot mean ({mu:.2f})"`.
  3. **Phương pháp C — Dị thường thời gian (`anomalies/temporal.py` — `M5.3`)**:
     - Nhận bảng thống kê của đợt khảo sát hiện tại (`current_survey`) và đợt khảo sát tham chiếu trước đó (`reference_survey`) trên cùng một `plot_id`.
     - Kiểm tra điều kiện tương thích: cùng `plot_id`, cùng loại camera/filter (`RGN`) và đã qua hiệu chỉnh phản xạ.
     - Ghép theo `unit_id` và tính độ suy giảm:
       $$\Delta \text{NDVI}_i = \text{NDVI}_{\text{current}, i} - \text{NDVI}_{\text{reference}, i}$$
       $$\text{DropRatio}_i = \frac{\text{NDVI}_{\text{reference}, i} - \text{NDVI}_{\text{current}, i}}{\max(\text{NDVI}_{\text{reference}, i}, \epsilon)}$$
     - Nếu $\Delta \text{NDVI}_i < -\text{min\_drop}$ (ví dụ giảm quá `0.10` hoặc giảm `> 15%`): tạo cảnh báo `anomaly_type = "temporal"`, `observed_value = current_ndvi`, `reference_value = reference_ndvi`, `reason = f"NDVI dropped by {abs(delta):.2f} ({drop_pct:.1f}%) compared to survey {ref_survey_id}"`.
  4. **Xếp hạng ưu tiên (`anomalies/ranking.py` — `M5.4`, `M5.5`)**:
     - Tính điểm ưu tiên `priority_score` (thang `0..100`) kết hợp **mức độ lệch (deviation)** và **diện tích/độ phủ ảnh hưởng (area)** với trọng số lấy từ `configs/anomaly.yaml`:
       $$\text{priority\_score} = \text{clip}\left(w_{\text{dev}} \cdot S_{\text{deviation}} + w_{\text{area}} \cdot S_{\text{area}} + w_{\text{repeat}} \cdot S_{\text{multi\_method}}, 0, 100\right)$$
     - Phân loại `severity`:
       - `high`: `priority_score >= 70` (hoặc giảm đột ngột nghiêm trọng)
       - `medium`: `40 <= priority_score < 70`
       - `low`: `priority_score < 40`
     - Sắp xếp danh sách cảnh báo theo `priority_score` giảm dần và đánh mã `ALT-001`, `ALT-002`, ...
  5. **Gom cụm vùng bất thường liền kề (`anomalies/clustering.py` — `M5.7`)**:
     - Dùng `shapely.ops.unary_union` (hoặc connected components trên lưới 2D) để tùy chọn gộp các ô bất thường liền cạnh nhau có cùng loại bất thường thành một Polygon cảnh báo lớn hơn, giúp chuyên gia không bị rối bởi hàng chục cảnh báo rời rạc trên cùng một vạt cây.

---

### CÔNG VIỆC 11: Xuất dữ liệu bàn giao theo Hợp đồng dữ liệu B → C (`M4.5`, `M5.6`)
- **Trạng thái**: ⏳ **CẦN LÀM (Người phụ trách: B2)**
- **Mục tiêu**: Xuất đầy đủ các file kết quả đúng cấu trúc và schema mà Backend/Frontend của Nhóm C (`POST /api/surveys/{id}/processing-results`) yêu cầu.
- **File cần tạo**:
  - `processing/src/agriscan/export/geotiff_export.py`
  - `processing/src/agriscan/export/geojson_export.py`
  - `processing/src/agriscan/export/csv_export.py`
  - `processing/src/agriscan/export/report_export.py`
- **Cách làm chi tiết**:
  1. **Trong `export/geojson_export.py` (`M5.6`)**:
     - Xuất file `processed/anomalies/alerts.geojson` chuẩn `FeatureCollection` (CRS `EPSG:4326`), mỗi `Feature` có `geometry` là Polygon thực (không được để `coordinates: []` rỗng) và `properties` khớp 100% với Hợp đồng Nhóm C:
       - `alert_code` (`"ALT-001"`), `survey_id`, `unit_id`, `index_name` (`"NDVI"`), `observed_value`, `reference_value`, `anomaly_type` (`"absolute"` | `"spatial"` | `"temporal"`), `severity` (`"low"` | `"medium"` | `"high"`), `priority_score`, `status` (`"PENDING"`), `reason`.
  2. **Trong `export/csv_export.py` (`M4.5`)**:
     - Xuất `processed/indices/statistics.csv`, `processed/indices/statistics.json` và `processed/anomalies/alerts.csv`.
  3. **Trong `export/report_export.py`**:
     - Xuất `processed/reports/processing_report.json` ghi nhận đầy đủ: `survey_id`, `plot_id`, `pipeline_version`, `config_version`, `status` (`"completed"` | `"needs_review"` | `"failed"`), thời gian bắt đầu/kết thúc, số ảnh `input`/`used`/`failed`, `crs`, đường dẫn các file sản phẩm (`orthomosaic`, `ndvi`, `vegetation_mask`, `statistics_csv`, `alerts_geojson`) và danh sách `warnings`.

---

### CÔNG VIỆC 12: Tích hợp Pipeline Một Lệnh, Kiểm thử `pytest` & Báo cáo Thực nghiệm (Lab 2, Lab 4)
- **Trạng thái**: ⏳ **CẦN LÀM (Người phụ trách: B1 + B2)**
- **Mục tiêu**: Đạt tiêu chí nghiệm thu **Mốc G2, G3, G4** — chạy toàn bộ quy trình từ thư mục khảo sát của Nhóm A ra bộ kết quả bàn giao cho Nhóm C chỉ bằng **một lệnh duy nhất**, có bộ unit test tự động và báo cáo khoa học.
- **File cần tạo / hoàn thiện**:
  - `processing/src/agriscan/pipeline/runner.py` & `processing/src/agriscan/cli.py`
  - `processing/tests/test_raw_reader.py`
  - `processing/tests/test_calibration.py`
  - `processing/tests/test_ndvi.py`
  - `processing/tests/test_masking.py`
  - `processing/tests/test_anomalies.py`
  - `processing/tests/test_export.py`
- **Cách làm chi tiết**:
  1. **Tích hợp lệnh CLI `process` trong `cli.py` và `runner.py`**:
     ```powershell
     python -m agriscan.cli process --input ..\assets --output processed/survey_2026-11-02_plot-A_001 --config configs/default.yaml
     ```
     - Luồng chạy tuần tự: `Validate Input` $\rightarrow$ `Read Metadata` $\rightarrow$ `Decode RAW 12-bit` $\rightarrow$ `Extract R-G-NIR Bands` $\rightarrow$ `Vignetting & Reflectance Calibration` $\rightarrow$ `Build Orthomosaic / Single-Frame Georeferenced Raster` $\rightarrow$ `Calculate NDVI/GNDVI/SAVI` $\rightarrow$ `Vegetation Mask & Grid Units` $\rightarrow$ `Zonal Statistics` $\rightarrow$ `Anomaly Detection (A + B + C)` $\rightarrow$ `Export GeoTIFF / GeoJSON / CSV / Report`.
     - Nếu có thể truyền thêm `--reference-survey <path_to_previous_processed_survey>` thì tự động kích hoạt thêm Phương pháp C (Dị thường thời gian).
  2. **Viết bộ kiểm thử tự động `pytest` trong `processing/tests/`**:
     - Kiểm tra giải mã RAW 12-bit (pack thử một mảng 12-bit bất kỳ thành 3-byte rồi gọi `decode_mapir_raw12` kiểm tra khôi phục chính xác 100%).
     - Kiểm tra `calculate_ndvi` với dữ liệu mẫu, mẫu số `0`, pixel `NaN`/`NoData`, hai mảng lệch kích thước.
     - Kiểm tra `spatial.py` khi độ lệch chuẩn $\sigma = 0$ hoặc danh sách unit rỗng.
     - Kiểm tra `geojson_export.py` sinh Polygon hợp lệ (`shapely.is_valid`) và đủ 11 trường hợp đồng với Nhóm C.
     - Chạy kiểm tra bằng lệnh: `pytest -v`.
  3. **Thực hiện 2 báo cáo phân tích thực nghiệm bắt buộc của Nhóm B (`05-Phan-cong-nhom-6.md`)**:
     - **Báo cáo Mốc G1 (Lab 2)**: Bảng số liệu phản xạ Red & NIR ở 3 thời điểm Sáng / Trưa / Chiều, chứng minh sai lệch $< 5\%$.
     - **Báo cáo Mốc G2–G4 (Lab 4)**: Biểu đồ chuỗi thời gian NDVI của lô cây bị ngừng tưới so với lô cây đối chứng qua 3 tuần, chỉ ra thời điểm thuật toán phát hiện bất thường cảnh báo sớm trước khi mắt thường thấy lá héo/vàng.
