# Teacher candidates — tuần 5, bản sơ bộ

Ngày 04/11/2026. Chọn bằng **Train Group CV AP**, tối đa hai họ khác nhau; không dùng Validation/Test chọn model.
Đây là ứng viên cho bước sau, không đồng nghĩa cần làm KD hoặc đã chứng minh distillation có lợi.
Không có calibration, threshold tuning hoặc soft-target generation trong công việc này.

## E2__mlp

- Cấu hình full Train: `StandardScaler → MLPClassifier(hidden_layer_sizes=(32,), alpha=0.001, batch_size=256, max_iter=1000, early_stopping=False, n_iter_no_change=20, random_state=42)`. Tham số khác là mặc định scikit-learn theo phiên bản trong metadata; outer folds có cấu hình riêng trong bảng parameters.
- CV mean ± std: AP **0.7335 ± 0.0142**, F1 **0.6315 ± 0.0130**;
  precision 0.8441, Recall 0.5048, FPR 1.76%.
- Validation bổ sung: AP 0.3762, F1 0.3824, FP 31, FN 11; không dùng để chọn.
- Pipeline serialized không nén: **38,225 bytes (37.33 KiB)**; chưa gồm reference/dependencies/Python runtime.
- PC batch 1: p50 1.812 ms, p95 2.327 ms.
- PC batch 128: p50 2.265 ms, p95 2.596 ms cho cả batch.
- Đo `.predict()` + `.predict_proba()` trên X đã tính; 1 thread, warm-up 5, repeat 30. Không tính parser/brand extraction/network/UI; không phải mobile benchmark.

## E2__hist_gradient_boosting

- Cấu hình full Train: `HistGradientBoostingClassifier(max_leaf_nodes=7, max_iter=150, learning_rate=0.1, l2_regularization=1.0, early_stopping=False, random_state=42)`. Tham số khác là mặc định scikit-learn theo phiên bản trong metadata; outer folds có cấu hình riêng trong bảng parameters.
- CV mean ± std: AP **0.7224 ± 0.0173**, F1 **0.6272 ± 0.0296**;
  precision 0.8317, Recall 0.5039, FPR 1.92%.
- Validation bổ sung: AP 0.4278, F1 0.4590, FP 23, FN 10; không dùng để chọn.
- Pipeline serialized không nén: **146,992 bytes (143.55 KiB)**; chưa gồm reference/dependencies/Python runtime.
- PC batch 1: p50 2.538 ms, p95 3.942 ms.
- PC batch 128: p50 4.689 ms, p95 5.608 ms cho cả batch.
- Đo `.predict()` + `.predict_proba()` trên X đã tính; 1 thread, warm-up 5, repeat 30. Không tính parser/brand extraction/network/UI; không phải mobile benchmark.

## Hợp đồng feature và artifact

Hai ứng viên cùng dùng `e2-brand-v0`, 20 features: 12 lexical + 8 brand theo đúng thứ tự trong metadata/bundle.
`id`, label, source, tier, split và fold không vào X. Lớp `[0,1]` = benign/phishing.
Cả hai dùng `predict_proba[:,1]` để xếp hạng, `estimator.predict` để quyết định, threshold mặc định 0,5.
Score chưa được hiệu chuẩn thành nguy cơ thực tế; chưa nên hiển thị một score như tỷ lệ bị lừa.

Artifact chung: `models/week5_e2_ablation.joblib`, key `models["mlp"]` / `models["hist_gradient_boosting"]`.
Bundle chứa cả năm model E2 và reference snapshot, vì vậy kích thước file bundle lớn hơn kích thước từng pipeline phía trên.
Tất cả model cuối chỉ fit **13.078 Train**, không thêm Validation. Inner-CV configs, versions, inputs/code/artifact hashes và runtime HEAD/dirty ở `tables/06_ablation_metadata.json`.
Reference raw hash phụ thuộc LF/CRLF; normalized LF hash được ghi riêng. Toàn bộ 37 entries còn draft.

## Giới hạn và điều kiện bước sau

- Recall CV quanh 50%; còn bỏ sót nhiều mẫu. Validation chỉ 24 positive, có shift và AP giảm; chưa tuyên bố tổng quát hóa.
- Brand rất thưa; reference chưa verified và có mẫu benign mismatch; dùng như thí nghiệm sơ bộ.
- Runtime HEAD hiện là base commit trước thay đổi local; metadata ghi dirty=true cùng code/source hashes, không giả đây là commit phát hành.
- Hưng cần xác nhận ID/folds/leakage và kết luận E1/E2 trước khi chốt. Đổi công thức/reference phải version và chạy lại phần liên quan.
- Nếu làm KD: Teacher sinh soft targets theo fold chỉ từ fitting partition; không lấy model full Train sinh target rồi chấm OOF trên cùng Train.
  So với Student hard-only cùng folds. Chưa có soft targets nào được tạo trong đợt này.
- Web/mobile gọi API có thể load bundle một lần và dùng `prediction.predict_url`. Offline mobile cần chuyển đổi model/runtime và kiểm tra parity riêng;
  joblib không chạy trực tiếp trên điện thoại. Chỉ làm KD khi có lợi ích tài nguyên đáng kể so với Student và model hiện tại.
