# AgriScan

- [Nhóm A — thu thập ảnh](acquisition/readme.md)
- [Nhóm B — xử lý ảnh, bản đồ và cảnh báo](processing/README.md)
- [Nhóm C — backend/frontend](platform/readme.md)

## Chạy nhóm B (Linux, tại thư mục gốc repo)

Cần Python 3.10+, Docker Engine đang chạy và tài khoản dùng được `docker info`; khuyến nghị RAM 16 GB trở lên.

```bash
python -m venv processing/.venv
processing/.venv/bin/python -m pip install -e ./processing
docker pull opendronemap/odm:3.5.6
processing/.venv/bin/agriscan process --input assets --experimental
```

Đầu vào: `assets/metadata.json`, `assets/raw/*.RAW` và JPG cùng lần chụp có GPS. RAW phải là MAPIR Survey3W RGN, các ảnh cùng khu vực có chồng lấn.

Kết quả: `processing/output/assets/manifest.json`, bản đồ NDVI/lưới và cảnh báo GeoJSON/CSV. Chạy lại thay bộ kết quả cũ khi thành công; thất bại giữ nguyên kết quả cũ. Không đưa ảnh hay output lên Git.

Chạy thử nhanh, không cần ảnh/Docker:

```bash
processing/.venv/bin/agriscan demo
```

Demo dùng dữ liệu giả và không chạy ODM. `--experimental` cho phép NDVI tương đối khi chưa có tấm chuẩn; chưa xác minh sai số phản xạ <5%, không so sánh khác buổi. Chi tiết lệnh/cấu hình: [processing/README.md](processing/README.md).
