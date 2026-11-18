# Báo cáo parity Python–Dart (E2 v1)

- schema: `e2-brand-v1` · tldextract (Python): `5.4.0`
- brand reference sha256: `6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6` (45 brand)
- tolerance cột liên tục: 0.000001; cột đếm/cờ: bằng tuyệt đối
- kết quả: **128/128** ca khớp hoàn toàn (parser trung gian + 20 đặc trưng)

| Nhóm | Số ca | Khớp |
| --- | ---: | ---: |
| official | 6 | 6 |
| brand_in_domain | 6 | 6 |
| brand_in_subdomain | 3 | 3 |
| brand_in_path | 2 | 2 |
| typo | 4 | 4 |
| homoglyph | 3 | 3 |
| idn | 3 | 3 |
| ip | 2 | 2 |
| normalization | 9 | 9 |
| suspicious | 2 | 2 |
| long | 1 | 1 |
| invalid | 6 | 6 |
| extra:idn_unicode | 13 | 13 |
| extra:ip_forms | 12 | 12 |
| extra:authority | 11 | 11 |
| extra:whitespace | 6 | 6 |
| extra:structure | 11 | 11 |
| extra:psl | 11 | 11 |
| extra:brand_edge | 10 | 10 |
| extra:percent | 5 | 5 |
| extra:size | 2 | 2 |

## Chênh lệch

Không có chênh lệch.

## Tái lập

```
cd mobile/packages/phishguard_features && dart pub get
dart test && dart run bin/parity_report.dart
```
