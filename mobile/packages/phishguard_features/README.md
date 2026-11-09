# phishguard_features (Dart)

Bản port Dart của extractor **E2 v1** (`e2-brand-v1`: 12 lexical + 8 brand features) cho Android/Flutter.
Nguồn chuẩn là code Python (`src/phishguard_vn/{url_parser,features,brand_features}.py`) và
`docs/mobile_feature_contract.md`. Khi lệch, Dart sửa theo Python, không ngược lại.

## Chạy

```bash
cd mobile/packages/phishguard_features
dart pub get
dart test test/units_test.dart          # không cần file PSL
dart test                                # đủ: cần assets/psl_icann_tldextract_5.4.0.txt
dart run bin/parity_report.dart          # ghi reports/mobile_parity_report.md
```

## Asset PSL
`assets/psl_icann_tldextract_5.4.0.txt` (6871 quy tắc, sha256 `fb8419c1…66c8f`) do
`scripts/export_psl_for_dart.py` sinh từ `tldextract==5.4.0`. Không sửa tay. Giữ LF
(`.gitattributes`: `mobile/packages/phishguard_features/assets/*.txt text eol=lf`).

## Dùng trong app
```dart
final ex = E2Extractor(PublicSuffixList.fromText(pslText), BrandReference.fromBytes(csvBytes));
final r = ex.extract('https://vietcombank-login.top/verify');
if (r.isClassifiable) { r.vector; /* 20 double theo e2FeatureOrder */ } else { r.errorReason; }
```
`brand_reference_v1.csv` KHÔNG sao chép tay: app lấy đúng file ở `src/phishguard_vn/resources/`
(kiểm sha256 so với file parity).

## Giới hạn đã biết (xem contract mục 10)
IDNA chỉ xấp xỉ UTS46 (không kiểm tra đầy đủ ký tự bị cấm); `isdigit` là xấp xỉ; casefold là
`toLowerCase` + `ß→ss`; IPv4-mapped IPv6 in dạng hex. Chỉ cam kết khớp trên các ca trong file parity.
