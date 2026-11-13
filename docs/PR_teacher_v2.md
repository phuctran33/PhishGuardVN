## Kết quả

Thêm nghiên cứu stacking và bundle **Teacher v2 candidate, chưa promoted**. Teacher v1 vẫn là mặc định.
PR này phụ thuộc #24; base tạm là `phuc-week6-teacher-v1` để nhóm chỉ review phần nghiên cứu mới.

Plan đăng ký trước kết quả: 11 pipeline, 53 cấu hình, cùng 13.078 Train IDs và 3 outer domain folds.
Tuning dùng 2 inner Group CV; meta learner dùng base group OOF; ngưỡng chỉ chọn từ fitting-side OOF.

| Pipeline | Mean outer AP |
|---|---:|
| Raw TF-IDF + SVM | 0,925628 |
| Hybrid canonical TF-IDF + E2 → SVM | 0,927713 |
| Canonical SVM + HistGB → LR | 0,930667 |
| SVM + HistGB + ExtraTrees → LR | 0,931131 |

Candidate hai nhánh tăng 0,005039 AP so với raw; CI 95% [-0,000570; 0,011136] vẫn chứa 0.
ExtraTrees tăng rất ít nhưng file/latency lớn. Chưa chứng minh candidate thắng chắc hoặc tổng quát tốt ngoài dataset.

## Stress và bổ sung theo review

- Thêm `https://`: raw SVM recall 77,77% → 25,41%; uppercase hostname → 3,23%. Đây là chẩn đoán tổng hợp dùng nhãn dataset.
- Stack hai nhánh có 0 label flips trong các phép stress đã thử. Điểm số vẫn có thể đổi do E2 raw; không tuyên bố bất biến mọi URL.
- Xác nhận hostname text thực sự đổi trên 13.078 URL; giữ path/query/userinfo/fragment/port/domain. Tái dùng outer models, kiểm cả native và policy fitting-OOF FPR 1%.
- HistGB CV lịch sử dùng auto nhưng <=8.719 fitting rows, thực tế không early-stop và đủ 300 vòng. **Giữ nguyên benchmark**, không rerun grid.
- Mọi fit candidate mới đặt `early_stopping=False`; full Train chạy đủ 300 vòng.
- Bảng source × label cho thấy các nguồn tách biệt hoàn toàn theo nhãn. Tách domain và bỏ cột source chưa loại source bias. Không sửa raw/nhãn/folds/features/reference.

## Bundle và kiểm chứng

- Canonical char 2–5 SVM C=1 + HistGB E2 → StandardScaler + LR C=0,1.
- Ngưỡng 0,6945740700635259 từ full-Train Group OOF, mục tiêu empirical FPR <=1%; không bảo đảm FPR ngoài mẫu.
- Bundle có reference snapshot, inference raw URL offline; score LR chưa calibrated. Canonical bỏ userinfo/fragment, có mất thông tin.
- Artifact: `models/teacher_v2_candidate.joblib`, 2.130.586 bytes.
- SHA256: `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`.
- 552 fits benchmark + 33 fits candidate thành công; 143.858 OOF rows audit PASS.
- Parity 13.078 inputs: score delta 0, labels khớp; single/batch delta <=1,67e-16 với atol=1e-12.
- Portable CLI chạy thật 5 URL, không dataset/report/reference CSV ngoài bundle.
- 12 FP/FN ở ba folds, đúng policy outer-fitting FPR 1%, có base scores/threshold/observation/hypothesis/next_check.
- Lần package đầu vướng TLD `.example` trong URL minh họa; sửa ví dụ và resume bundle đã freeze, không retrain/overwrite model.
- Full local research suite: **500 passed, 1 historical skip**, 2 historical L1 warnings. Focused sau cập nhật provenance: **53 passed**, không skip.
- Workflow hiện có thêm stacking fixtures bắt buộc, CI không train project data hoặc gọi website. CI thực xem head PR; số local không thay CI.

## Đánh giá bổ sung sau freeze

| Scope | AP | Recall | FPR | TP/FN/FP/TN |
|---|---:|---:|---:|---|
| Validation: 24 phishing / 1.561 benign | 0,5549 | 62,50% | 0,897% | 15/9/14/1547 |
| External historical hostname: 92 / 7 | 0,9813 | 40,22% | 14,29% | 37/55/1/6 |

Vẫn bỏ sót 55/92 phishing; external FPR chỉ dựa trên 7 benign. 68 pending không chấm; cohort 92 là subset của 99.
Các scope đã từng được quan sát, không dùng chọn lại model/ngưỡng. Không Official Test, KD, export hoặc Android.

Báo cáo: [teacher_v2_stacking.md](https://github.com/phuctran33/PhishGuardVN/blob/phuc-teacher-v2-stacking/reports/teacher_v2_stacking.md).
Flow code và cách chạy: [teacher_v2_handoff.md](https://github.com/phuctran33/PhishGuardVN/blob/phuc-teacher-v2-stacking/docs/teacher_v2_handoff.md).
Nhóm quyết định promotion riêng; PR này không thay Teacher v1 hoặc tự merge.
