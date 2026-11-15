# Báo cáo suy luận Dart SVM của Teacher v2

> **Lưu ý về trạng thái:** Đây là báo cáo lịch sử ghi nhận giai đoạn triển khai
> Teacher v2 SVM-only. Các kết quả 289 Dart tests và 41/41 SVM reference
> cases bên dưới thuộc giai đoạn đó, không phải trạng thái kiểm thử mới nhất.
>
> Sau báo cáo này, Dart-native full Teacher v2 inference đã được triển khai,
> bao gồm SVM, HistGradientBoosting và Meta Logistic Regression. Full pipeline
> parity đạt 41/41 fixtures; Dart test suite mới nhất đạt 294/294 tests.
>
> Xem trạng thái triển khai hiện tại, phạm vi xác minh và các giới hạn còn lại tại:
> [`docs/week6_teacher_deployment_assessment.md`](../docs/week6_teacher_deployment_assessment.md).


## Phạm vi và triển khai

Đã triển khai `SvmModel` thuần Dart, chỉ dành riêng cho nhánh SVM của `teacher-stacking-v2` đã được đóng băng (frozen).

Triển khai này tải mô hình JSON đã được export (`dart-svm-v1`), thực hiện canonicalization đầu vào URL, tạo character n-gram dựa trên Unicode code point với độ dài từ 2–5, đếm số lần xuất hiện của các feature chồng lấn (overlapping features), áp dụng sublinear TF, các giá trị IDF đã export, L2 normalization và tính toán LinearSVC signed decision margin (`dot + intercept`).

HistGB và Meta LR inference chưa được triển khai trong Dart. Đây **không phải là sự tương đương inference hoàn chỉnh của Teacher (full Teacher inference parity)**.

Python exporter tạo ra các tệp sau:

- `artifacts/teacher_v2_android/dart_svm_model.json`
- `artifacts/teacher_v2_android/manifest.json`
- `artifacts/teacher_v2_android/svm_vocabulary.json`
- `artifacts/teacher_v2_android/teacher_numeric.npz`
- `mobile/packages/phishguard_features/test/fixtures/svm_reference_margins.json`

Reference fixture chứa 41 URL hợp lệ từ `docs/mobile_parity_cases.json`, với các giá trị margin kỳ vọng được tạo bằng `decision_function` của Python SVM đã được huấn luyện (fitted).

## Xác minh model và quá trình export

Quá trình export và verification đã được thực hiện trên máy local trong môi trường CPython 3.11.7 đã khóa phiên bản (locked environment).

Kết quả:

- Export: PASS.
- Artifact hashes và các mảng SVM JSON: PASS.
- NPZ và các tham số HistGB: PASS.
- Kích thước vocabulary: 37,106.
- Số lượng HistGB trees đã export: 300.
- Tổng số HistGB nodes: 8,700.
- Số lượng Python reference cases được tạo: 41.
- Thứ tự feature E2 đã khóa (Locked E2 feature order): 20 features, không thay đổi.
- Teacher threshold được giữ nguyên: `0.6945740700635259`.
- Sai số tuyệt đối lớn nhất khi tái dựng Python SVM (Python SVM reconstruction): `0.0`.

Quá trình export nhánh SVM không làm thay đổi Teacher bundle đã đóng băng, model weights, threshold, các công thức E2 hoặc thứ tự feature.

## Triển khai Dart và xác minh parity

Triển khai Dart sử dụng:

- Unicode code-point slicing thông qua Dart `String.runes`.
- Character n-gram với độ dài từ 2–5.
- Đếm số lần xuất hiện của các n-gram chồng lấn (Overlapping n-gram counts).
- Sublinear TF: `1 + ln(count)`.
- Các giá trị IDF float64 đã export.
- L2 normalization.
- LinearSVC coefficients và intercept.

Kết quả verification trên máy local:

| Kiểm tra | Kết quả |
| ----------------------------- | --------------------------------------- |
| `dart format` | Hoàn tất; 0 files changed trong lần chạy cuối |
| `dart test` | PASS: 289 tests |
| Python reference parity của SVM | PASS: 41/41 cases |
| Sai số margin tuyệt đối lớn nhất | `8.881784197001252e-16` |
| Parity tolerance | `1e-6` |
| `dart analyze` | 7 diagnostics: 1 warning và 6 info |

Kết quả reference parity trên 41 trường hợp xác nhận rằng triển khai Dart SVM cho kết quả tương đồng với Python SVM reference trên các trường hợp fixture đã được tạo.

Kết quả này không chứng minh full Teacher inference parity hoặc tính chính xác đối với tất cả URL có thể xảy ra.

## Đánh giá tính chính xác và các khác biệt đã biết

### Xử lý ký tự (Character processing)

Triển khai Dart sử dụng Unicode code point thay vì UTF-16 code unit để thực hiện character n-gram slicing.

Triển khai này thay thế các chuỗi liên tiếp gồm từ hai Python-compatible whitespace code point trở lên bằng một dấu cách ASCII, đồng thời giữ nguyên các whitespace xuất hiện đơn lẻ. Đầu vào không bị trim.

Kết quả so sánh reference trên 41 trường hợp local đã PASS trong phạm vi tolerance được công bố.

### URL canonicalization

Triển khai tuân theo source contract đối với hierarchical URLs:

- Loại bỏ scheme, userinfo và fragment.
- Giữ nguyên path và query.
- Loại bỏ các default HTTP và HTTPS ports.
- Đặt IPv6 literals trong dấu ngoặc vuông.

### Giới hạn IDNA / UTS-46

**Tính tương đương IDNA/UTS-46 vẫn chưa được giải quyết.**

Triển khai Dart sử dụng `hostToAscii` hiện có trong package. Đây là một phiên bản xấp xỉ, dựa trên NFKC/lowercase và một số kiểm tra IDNA2008 có giới hạn.

Chưa có bằng chứng chứng minh triển khai này tương đương với Python `idna.encode(host, uts46=True)` đối với tất cả Unicode hostnames.

Các trường hợp liên quan đến UTS-46 mapping, disallowed code points, contextual rules hoặc các labels bất thường có thể tạo ra kết quả khác biệt. Không được tuyên bố có exact canonicalization parity đối với các trường hợp Unicode hostname chưa được kiểm thử.

### Giới hạn về runtime và tài nguyên

JSON loading, peak memory usage, model initialization time và inference latency vẫn chưa được benchmark trên thiết bị Android thực tế.

Kết quả hiện tại chỉ xác minh inference ở cấp Dart package, không phải kết quả đánh giá hiệu năng trên thiết bị thực tế.

## Tính khả thi của offline inference

Teacher đã được đóng băng bao gồm nhiều thành phần:

1. Canonical text và TF-IDF character features, được đưa vào LinearSVC.
2. HistGradientBoosting sử dụng 20 E2 numeric features.
3. Một mô hình meta-model gồm StandardScaler và LogisticRegression, kết hợp điểm số của hai base models.

Nhánh SVM hiện đã có triển khai inference thuần Dart hoạt động được, với reference parity trên 41 fixture URLs.

Các nhánh HistGB và Meta LR vẫn chưa được triển khai trong Dart. Vì vậy, triển khai hiện tại không thể tái tạo toàn bộ Teacher score hoặc áp dụng final Teacher decision threshold.

Các bước export và reconstruction verification thành công cung cấp cơ sở để tiếp tục đánh giá một triển khai offline, nhưng không chứng minh rằng toàn bộ Teacher đã được chuyển đổi sang ONNX, TFLite hoặc một Android runtime khác.

Các công việc tiếp theo phải xác minh toàn bộ score pipeline, class ordering, threshold behavior và end-to-end Python–Android inference equivalence trước khi tuyên bố hỗ trợ đầy đủ Teacher ở chế độ offline.

## Trạng thái kiểm thử (Test status)

Đã xác minh trên máy local:

- Python exporter: PASS.
- Python artifact verifier: PASS.
- Python SVM reconstruction: sai số tuyệt đối lớn nhất là `0.0`.
- Dart tests: 289 tests passed.
- Dart SVM reference parity: 41/41 passed.
- Sai số parity tuyệt đối lớn nhất: `8.881784197001252e-16`.
- Dart analyzer: còn 7 diagnostics không nghiêm trọng (non-fatal).

## Công việc còn lại (Remaining work)

1. Giải quyết hoặc ghi rõ giới hạn về khả năng tương thích IDNA/UTS-46.
2. Triển khai và xác minh HistGB inference trong offline runtime dự kiến sử dụng.
3. Triển khai và xác minh Meta LR inference cùng final threshold behavior.
4. So sánh toàn bộ Teacher scores và labels giữa Python và Android.
5. Benchmark model size, memory, initialization và inference latency trên Android.
6. Chuẩn bị kế hoạch Student offline cho Week 7, bao gồm các biện pháp bảo vệ data split (data-split safeguards), mục tiêu về model size/runtime và các tiêu chí đánh giá (evaluation criteria).

## Kết luận (Conclusion)

Nhánh Teacher v2 SVM đã được export và triển khai bằng Dart thuần. Decision margins của mô hình khớp với Python reference trên toàn bộ 41 valid fixture cases đã được tạo, trong phạm vi tolerance `1e-6`.

Đây là một cột mốc đã được xác minh đối với inference của nhánh SVM (verified SVM-branch inference milestone). Kết quả này không phải là tuyên bố về full Teacher inference parity, triển khai Android offline hoàn chỉnh hoặc thành công trong việc chuyển đổi sang ONNX/TFLite.