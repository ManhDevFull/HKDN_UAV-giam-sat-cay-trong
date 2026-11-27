# Nhóm B — RAW → bản đồ → cảnh báo

Lệnh dưới chạy **tại thư mục gốc repo**, Linux, Python 3.10+, Docker hoạt động (`docker info`). Khuyến nghị RAM 16 GB, đĩa trống tùy số ảnh.

## Cài một lần

```bash
python -m venv processing/.venv
processing/.venv/bin/python -m pip install -e ./processing
docker pull opendronemap/odm:3.5.6
```

## Chạy ảnh nhóm A

Đặt `metadata.json` trong `assets/`, ảnh MAPIR Survey3W **RGN** trong `assets/raw/`. Giữ RAW + JPG đi kèm có GPS/EXIF; không đổi tên làm mất cặp ảnh. Cần ít nhất 3 vị trí có ảnh cùng cảnh, đủ chồng lấn. JPG chỉ cung cấp metadata, không tính NDVI từ JPG.

```bash
processing/.venv/bin/agriscan process --input assets --experimental
```

Tùy chọn: `--output processing/output/khao-sat`, `--boundary assets/plot.geojson` (Polygon WGS84), `--config processing/configs/workflow.yaml`.

Sửa `processing/configs/workflow.yaml`: `grid.cell_size_m` (mặc định 1 m), `anomaly.absolute_threshold` (A, NDVI <0.35), `anomaly.spatial_z_threshold` (B, z-score <-1.5 trong cùng plot), trọng số `anomaly.ranking`. Truyền `--config` để dùng file đã sửa; không truyền dùng cấu hình mặc định đóng gói.

`--experimental`: chưa có tấm chuẩn, chỉ sàng lọc NDVI tương đối; ngưỡng cần kiểm chứng thực địa. Chưa xác minh sai số phản xạ <5%, không so sánh khác buổi, không kết luận bệnh cây.

## Lấy kết quả cho nhóm C

Trong `processing/output/assets/` (hoặc `--output`):

- `manifest.json`: đường dẫn tương đối tới toàn bộ sản phẩm.
- `maps/orthomosaic.tif`, `ndvi.tif`, các mask đất/bóng/thực vật và raster ID ô.
- `maps/grid.geojson`, bảng thống kê ô CSV/JSON; `maps/ndvi_preview.png` xem nhanh.
- `alerts/alerts.geojson`, `alerts.csv`: A/B, mức cảnh báo và điểm ưu tiên 0–100.
- `summary.json`, `preprocessing.json`, `workflow.yaml`, `logs/`: chất lượng, ảnh bị loại và cấu hình thực chạy.

GeoJSON WGS84; raster CRS chiếu theo mét. Nhóm C ánh xạ mã survey/plot/unit sang UUID backend trước khi nhập; pipeline xuất file, chưa tự gọi API.

Chạy lại cùng đầu vào ghi đè **một bộ** kết quả khi thành công; lỗi giữ kết quả trước. Thư mục chứa file tự thêm sẽ không bị ghi đè. Dữ liệu/output bị ignore, cấu hình và code được commit.

## Chạy thử / kiểm tra lỗi

```bash
processing/.venv/bin/agriscan demo
processing/.venv/bin/agriscan validate assets
```

Demo dùng dữ liệu giả, xuất `processing/output/demo/`, không chạy ODM. Nếu ảnh thật lỗi, xem `processing/output/assets.failure.json`: thiếu GPS cần JPG đi kèm; ảnh thiếu overlap/tách khối cần bộ ảnh cùng cảnh; thiếu RAM giảm `mosaicking.max_concurrency`/`pc_quality`. Không xuất cảnh báo khi bản ghép không đạt ≥90% ảnh đã chuẩn bị. Không có biên plot thì chưa kiểm chứng vùng hổng ngoài footprint.

Có orthomosaic tuyến tính R/G/NIR float32 hợp lệ, tag `units=relative_signal`, `band_order=red,green,nir`:

```bash
processing/.venv/bin/agriscan analyze duong-dan/orthomosaic.tif --survey-id survey-001 --plot-id plot-A --experimental
```

Kiểm tra code (không cần Docker):

```bash
processing/.venv/bin/python -m pip install -e './processing[dev]'
processing/.venv/bin/python -m pytest processing/tests -q
```

ODM ghim [3.5.6](https://github.com/OpenDroneMap/ODM/releases/tag/v3.5.6); quy ước GPS: [geo.txt](https://docs.opendronemap.org/geo/).
