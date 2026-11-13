## Vấn đề và kết quả

Teacher v1 raw SVM có CV AP tốt nhưng nhạy định dạng URL. PR này giữ v1 và thêm nghiên cứu cùng bundle **Teacher v2 candidate chưa promoted**.
Phụ thuộc PR #24; base tạm là phuc-week6-teacher-v1 để chỉ review thay đổi nghiên cứu.

- Đăng ký plan trước kết quả: 11 pipeline/53 cấu hình; cùng13.078 Train IDs/3outer domain folds/2inner Group CV.
- 552 fits benchmark +33 fits candidate, 0 failed;143.858 outer OOF rows audit PASS.
- Raw SVM AP0,925628; SVM+HistGB→LR AP0,930667. Delta0,005039, CI95%[-0,000570;0,011136]: chưa chứng minh thắng chắc.
- ExtraTrees thứ ba tăng rất ít, CI chứa0 nhưng file/latency lớn. Giữ candidate hai nhánh.
- Stress thêm https: raw recall77,77%→25,41%; uppercase hostname→3,23%.
  Candidate outer stack có0 label flips ở các phép thử; điểm số vẫn đổi do một số E2 raw. Không tuyên bố bất biến mọi URL.

## Bổ sung theo review, không rerun grid

- HistGB CV lịch sử auto nhưng <=8.719 fitting rows, effective early stop=False, đủ300 vòng; giữ model/metric.
- Mọi fit candidate mới đặt early_stopping=False, full Train chạy300 vòng.
- Kiểm hostname text thực đổi ở13.078 URL, giữ path/query/userinfo/fragment/port/domain;
  tái dùng outer models, kiểm cả native và policy Train OOF FPR1%.
- Bảng source×label cho thấy nguồn phân tách hoàn toàn theo nhãn. Bỏ source và tách domain chưa loại source bias.
  Không sửa raw/labels/folds/features/reference.

## Bundle và operating point

- Canonical char2–5 SVM C1 +HistGB E2→StandardScaler+LR C0,1.
- Threshold 0.6945740700635259 chọn từ full-Train Group OOF với mục tiêu FPR1%, không bảo đảm FPR ngoài mẫu.
- Artifact models/teacher_v2_candidate.joblib, SHA256 63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1.
- Raw URL vào toàn pipeline offline, bundled reference; score LR chưa calibrated.
- Bỏ scheme/default port/userinfo/fragment; giữ path/query case/percent escapes. Userinfo/fragment là giới hạn mất thông tin.
- Default v1 lock/bundle/adapter/CLI nguyên byte; không promotion/merge.

## Kiểm chứng

- Parity13.078 inputs: score delta0, labels khớp; single/batch score delta<=1,67e-16 (atol1e-12), portable CLI5URL thật.
- Lần package đầu vướng URL ví dụ TLD.example; sửa ví dụ và resume bundle đã freeze, **không retrain/overwrite bundle**.
- 12 FP/FN đúng outer-policy1%, ba folds, có base scores/threshold/observation/hypothesis/next_check.
- Full local research suite: **500 passed,1 historical skip**,2 historical L1 warnings; không skip mới.
- Workflow hiện có thêm >=53 stacking fixtures không skip. CI thực theo head PR, số local không thay CI.

## Đánh giá bổ sung sau freeze

Validation1585(24/1561): AP0,5549;recall62,50%;FPR0,897%;TP/FN/FP/TN15/9/14/1547.
External99 historical hostnames(92/7): AP0,9813;recall40,22%;FPR14,29%;37/55/1/6.
Vẫn bỏ sót55/92 phishing; FPR chỉ7benign. 68pending không chấm;92 là subset99, không coi độc lập.
Không dùng Validation/external chọn model/ngưỡng; không Official Test/KD/Android/export.

Báo cáo: reports/teacher_v2_stacking.md. Handoff/CLI: docs/teacher_v2_handoff.md.
Nhóm review và quyết định promotion riêng; không có tuyên bố tổng quát tốt ngoài dataset.
