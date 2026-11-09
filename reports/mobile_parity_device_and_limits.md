# Parity Python–Android (E2 v1): kết quả trên thiết bị và giới hạn đã biết

Bổ sung cho `reports/mobile_parity_report.md` (báo cáo tự sinh từ Dart VM). Issue #18.

## 1. Phạm vi
- Schema: `e2-brand-v1` (12 lexical E1 + 8 brand), thứ tự 20 cột theo `docs/mobile_feature_contract.md`.
- Reference: `brand_reference_v1.csv`, 45 brand, sha256 `6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6`.
- PSL: snapshot ICANN của `tldextract 5.4.0`, 6871 quy tắc, sha256 `fb8419c17a533dfdd57199da1cef1481974119fe23ce7c478af3d12eb8466c8f`.
- Nguồn kỳ vọng: Python (`docs/mobile_parity_cases.json`, 47 ca frozen; `docs/mobile_parity_cases_extra.json`, 81 ca bổ sung, kỳ vọng sinh từ code Python, không tính tay).
- Không thay công thức hay reference Python để làm parity pass.

## 2. Kết quả

| Môi trường | Frozen | Extra | Tổng | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| Dart VM (`dart test`, macOS) | 47/47 | 81/81 | 128/128 | 274 test pass |
| Android Emulator (Pixel 6, Android 15 / API 35, arm64) | 47/47 | 81/81 | 128/128 | màn hình Parity trong app, 87 ms |

So từng cột của 20 đặc trưng và các giá trị trung gian của parser (`is_valid`, `error_reason`, `hostname`,
`registrable_domain`, `subdomain`, `path`, `query`, `is_ip`). Tolerance: `1e-6` cho `entropy` và `brand_typo_score`;
các cột đếm/cờ phải bằng tuyệt đối. URL không hợp lệ phải trả "không phân loại được" kèm `error_reason`, không trả số giả.

Công cụ: Flutter 3.47.9, Dart 3.13.7. Python 3.12.6 (pyenv), tldextract 5.4.0.

## 3. Lỗi đã phát hiện và đã sửa (phía Dart)
| Ca | Hiện tượng | Nguyên nhân | Xử lý |
| --- | --- | --- | --- |
| `emoji_host` (`http://😀.com/`) | Python: `invalid_hostname`; Dart: hợp lệ (host Punycode) | `hostToAscii` chưa kiểm tra ký tự bị cấm của IDNA2008 | Thêm kiểm tra nhãn (`_validIdnaLabel`) trong `lib/src/idna.dart`. Python không đổi. |

## 4. Giới hạn đã biết và lỗi còn tồn tại
Không có ca nào trong 128 ca còn lệch. Các điểm dưới đây là chỗ Dart chỉ xấp xỉ Python; parity chỉ được cam kết trên các ca đã kiểm.

| # | Điểm | Mô tả | Ảnh hưởng | Trạng thái |
| --- | --- | --- | --- | --- |
| 1 | IDNA | `hostToAscii` xấp xỉ `idna.encode(uts46=True)`: lower + NFKC + Punycode + kiểm nhãn gần đúng; không cài đủ bảng UTS46/IDNA2008 | Ký tự hiếm có thể lệch (hợp lệ/không hợp lệ) | Mở, chỉ cam kết trên ca parity |
| 2 | `isdigit` | Python `str.isdigit()` = Nd + một số chữ số No; Dart dùng Nd + danh sách các khoảng thường gặp | `digit_cnt` có thể lệch với ký tự số hiếm | Mở |
| 3 | casefold | Dart: `toLowerCase` + `ß→ss`; Python `casefold()` | Chỉ khác ở vài ký tự hiếm; sau NFKD chỉ giữ `[a-z0-9]` | Mở, rủi ro thấp |
| 4 | IPv4-mapped IPv6 | Khớp với Python 3.12.6 (ca `ipv6_v4_mapped` pass); có thể lệch nếu sinh lại parity bằng Python ≥ 3.13 | `hostname` trung gian; không đổi 20 feature | Mở, tùy phiên bản Python |
| 5 | `urlsplit` | Khớp với Python 3.12.6; chưa kiểm với bản Python khác | Ca `[...]` bất thường | Mở, cần kiểm thêm phiên bản Python |
| 6 | PSL | Cố định snapshot `tldextract 5.4.0`; đổi PSL = đổi `dom_len` và mọi brand feature | Phải sinh lại parity khi đổi | Theo contract mục 11 |
| 7 | Phạm vi thiết bị | Mới chạy trên 1 emulator arm64 | Chưa kiểm x86/điện thoại thật | Mở |
| 8 | Công cụ debug | Cuối `flutter run` có `DartDevelopmentServiceException ... Connection refused` | Chỉ ảnh hưởng hot reload/debugger; app và parity chạy bình thường | Không ảnh hưởng deliverable |

## 5. Cách tái lập
```bash
# 1) Sinh kỳ vọng Python (cần Python 3.12.6 và tldextract 5.4.0)
python scripts/05_make_parity_vectors.py --check
python scripts/05_make_parity_extra.py

# 2) Parity trên Dart VM
cd mobile/packages/phishguard_features
dart pub get
dart test
dart run bin/parity_report.dart          # ghi reports/mobile_parity_report.md

# 3) Parity trên Android Emulator
cd ../../..
bash mobile/tool/sync_assets.sh
cd mobile/app
flutter pub get && flutter analyze && flutter test
flutter run -d emulator-5554             # mở biểu tượng ✓ → "Chạy parity"
```

## 6. Chưa làm (ngoài phạm vi #18)
- Chạy model trên Android (ONNX/TFLite): thuộc #20 và tuần 7.
- Parity trên điện thoại thật và x86.