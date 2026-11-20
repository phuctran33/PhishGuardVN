# phishguard_android

Ứng dụng Android phân tích URL **offline** bằng Teacher v2 (`teacher-stacking-v2`) và vẫn giữ trang kiểm tra parity E2.
Dùng package Dart `../packages/phishguard_features`. Không gọi FastAPI, không dùng mạng, không truy cập website.

## Luồng

`nhập URL -> kiểm đầu vào -> extractor E2 phân loại được? -> TeacherV2OfflineModel.predict -> kết quả`

- Đầu vào bị từ chối theo hợp đồng Teacher: rỗng, ký tự điều khiển, khoảng trắng hai đầu (không tự cắt bỏ).
- URL mà parser không phân loại được: "Không phân loại được" kèm mã lỗi, không có nhãn.
- Nhãn lấy theo quy tắc đóng băng `score >= 0.6945740700635259`. Điểm **chưa hiệu chuẩn**, không phải phần trăm an toàn.
- Khởi tạo thất bại (thiếu asset, JSON hỏng, SHA-256 hoặc hợp đồng lệch...): màn hình lỗi, **không có ô phân tích**.

## Chạy

```bash
# từ root repo
bash mobile/tool/sync_assets.sh          # chép PSL, brand reference, file parity và Teacher v2 vào assets/
(cd mobile/packages/phishguard_features && dart test)
cd mobile/app
flutter pub get
flutter analyze
flutter test
flutter run -d <id thiết bị hoặc emulator>
```

`assets/*` (trừ `.gitkeep`) là bản sao do `sync_assets.sh` tạo, không commit. Nguồn duy nhất:

| Asset | Nguồn |
| --- | --- |
| `psl_icann_tldextract_5.4.0.txt` | `mobile/packages/phishguard_features/assets/` |
| `brand_reference_v1.csv` | `src/phishguard_vn/resources/` |
| `mobile_parity_cases*.json` | `docs/` |
| `dart_svm_model.json`, `dart_teacher_v2_model.json`, `teacher_v2_manifest.json` | `artifacts/teacher_v2_android/` |

`svm_vocabulary.json` và `teacher_numeric.npz` **không** đóng gói vì runtime Dart không đọc chúng.

## Kiểm toàn vẹn khi khởi động

1. Manifest phải khớp hằng số đóng băng trong `lib/src/teacher_contract.dart` (model version, threshold, rule,
   thứ tự `svm`/`hist`, class mapping, 20 đặc trưng, SHA-256 của bundle gốc và brand reference).
2. `brand_reference_sha256` của manifest phải bằng sha256 của reference mà extractor E2 đã nạp.
3. Kích thước và SHA-256 của hai JSON được kiểm trên **bytes thô** so với manifest, rồi mới giải mã.

Lưu ý: manifest nằm cùng gói ứng dụng, nên kiểm này phát hiện file hỏng hoặc lệch phiên bản, không phải cơ chế chống giả mạo.
