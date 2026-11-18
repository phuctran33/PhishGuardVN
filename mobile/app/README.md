# phishguard_android

Ứng dụng Android demo extractor **E2 v1** (20 đặc trưng URL). Dùng package Dart
`../packages/phishguard_features`. Chưa có mô hình: app chỉ trích xuất đặc trưng và có màn hình
**parity** chạy bộ ca của Python ngay trên thiết bị. Không truy cập mạng, không gửi URL đi đâu.

```bash
# từ root repo
bash mobile/tool/sync_assets.sh          # chép PSL, brand reference, file parity vào assets/
cd mobile/app
flutter pub get
flutter analyze
flutter test
flutter run                               # chọn Android Emulator đang chạy
```

`assets/*` (trừ `.gitkeep`) là bản sao do `sync_assets.sh` tạo, không commit. Nguồn duy nhất:
`src/phishguard_vn/resources/brand_reference_v1.csv`, `docs/mobile_parity_cases*.json`,
`mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt`.
Khi app khởi động, sha256 của brand reference được so với bản đã freeze; lệch thì app báo lỗi.
