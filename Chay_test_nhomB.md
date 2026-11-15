### Cách chạy kiểm tra (Test) ngay trên Terminal

Mở PowerShell tại thư mục `processing` và kích hoạt `.venv`:
```powershell
cd d:\University\HK126\HKDN\HKDN_UAV-giam-sat-cay-trong\processing
.\.venv\Scripts\Activate.ps1
```

1. **Chạy tổng hợp cả 3 mục (nạp cấu hình + validate `assets/` + giải mã thử ảnh `.RAW` đầu tiên)**:
   ```powershell
   python -m agriscan.cli run --config configs/default.yaml --input ..\assets
   ```
2. **Kiểm tra chi tiết tính hợp lệ của thư mục khảo sát `assets/` (Mục 2)**:
   ```powershell
   python -m agriscan.cli validate ..\assets
   ```
3. **Giải mã và xem thông số chi tiết 1 file `.RAW` thực tế của MAPIR Survey3W (Mục 3)**:
   ```powershell
   python -m agriscan.cli read-raw ..\assets\raw\2026_1102_041147_001.RAW --metadata ..\assets\metadata.json
   ```
4. **Chạy thử lệnh `process-survey` để tách kênh và xuất ảnh xem trước `.png` từ file `.RAW` thật trong `assets/raw/`**:
   ```powershell
   process-survey ..\assets\raw\2026_1102_041147_001.RAW --output output/real-raw-001
   ```