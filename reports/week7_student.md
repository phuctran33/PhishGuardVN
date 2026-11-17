# Student tuần 7 — kết quả phát triển ban đầu

**Trạng thái: experimental, chưa thay Teacher, chưa chốt release.**
Căn cứ: [protocol](../docs/week7_student_protocol.md) và kế hoạch Student mới nhất.
Teacher v2, threshold, E1/E2, reference và preprocessing phát hành giữ nguyên.

## Đã chạy

- Train: 13.078 mẫu (2.074 phishing); Validation: 1.585 mẫu (24 phishing).
- Không overlap ID/domain/canonical giữa hai tập. Loại 2 Train IDs theo eligibility,
  có lý do trong exclusions.csv; không loại mẫu vì Teacher đoán sai.
- Tạo raw Teacher targets trên Train bằng released Teacher v2.
- Một kiến trúc nhỏ (8.192 character TF-IDF + LR), hai cách học: hard-only và mixed KD.
- C=1, alpha=0,5, seed=42; không grid search hoặc thử thêm model sau khi xem kết quả.
- Xuất JSON; đối chiếu mọi score và label trên 1.585 Validation inputs với sklearn
  (atol=1e-12). Có tests trên URL tổng hợp/Unicode/IP/port/userinfo/path-query và input lỗi.
- Đo desktop URL-to-score latency; số đo nằm ở latency.csv, không phải số đo Android.
- Official Test/external chưa chạy trong phần Student.

## Kết quả Validation

| Model | AP | Recall | FPR | F1 | TP / FP / TN / FN |
|---|---:|---:|---:|---:|---|
| Teacher v2, ngưỡng phát hành | 0,5549 | 62,50% | 0,90% | 0,5660 | 15 / 14 / 1547 / 9 |
| Student hard-only, ngưỡng chọn Validation | 0,2926 | 33,33% | 0,90% | 0,3478 | 8 / 14 / 1547 / 16 |
| Student mixed KD, ngưỡng chọn Validation | 0,3046 | 33,33% | 0,83% | 0,3556 | 8 / 13 / 1548 / 16 |

Student thresholds: hard-only 0,5486056188894293; KD 0,564855787905593.
Teacher threshold không đổi: 0,6945740700635259.
Bảng benchmark.csv còn có ngưỡng cố định 0,5: cả hai Student có Recall 37,50%,
FPR 1,41%, TP=9, FP=22, TN=1539, FN=15.
Các hàng khác threshold không được diễn giải thành cải thiện kiến trúc.

JSON hard-only: 495.557 bytes; KD: 495.753 bytes, xấp xỉ 0,473 MiB/model.
Đây là kích thước model JSON, không phải RAM hoặc kích thước APK.
AP là sklearn average_precision_score, không phải PR-AUC hình thang.

## Kết luận hiện tại

KD được chọn **để thử tính khả thi Android** vì AP cao hơn hard-only 0,0120 trên
Validation. Cả hai chỉ phát hiện 8/24 phishing ở ngưỡng theo ngân sách FPR.
Student chưa giữ được chất lượng Teacher; **NO-GO thay Teacher làm mặc định**.

Agreement với Teacher khoảng 98,5% dễ gây hiểu nhầm: Teacher chỉ báo 29 mẫu dương
trên 1.585 Validation; dự đoán tất cả benign cũng đạt agreement khoảng 98,17%.
Hard-only có agreement và score MAE tốt hơn KD ở operating point đã chọn dù AP thấp hơn.
Không dùng agreement cao hoặc cải thiện AP nhỏ này làm bằng chứng KD thành công.
Giả thuyết mô hình nhỏ mất tín hiệu chỉ là giả thuyết, chưa có ablation chứng minh.

## Giới hạn

- Targets là in-sample của Teacher đã fit Train, không cross-fit/OOF KD.
- Validation được dùng chọn model và threshold, đã được nhóm xem ở tuần trước;
  metrics là development metrics, không phải final generalization evidence.
- Chỉ 24 positives; một seed, một cấu hình; chưa có confidence interval cho chênh lệch.
- Bảng source × label cho thấy toàn bộ phishing từ tinnhiemmang, các nguồn khác benign;
  domain disjoint không loại bỏ source bias. Nhãn PhishVN có hạn chế ngữ nghĩa/nguồn.
- Chưa kiểm tra toàn bộ near-duplicates giữa các domain khác nhau.
- Chưa có evaluation độc lập hoặc Android/Dart parity, latency/RAM/battery/APK.
- Không đổi nhãn/dữ liệu để làm đẹp kết quả. Không có tuyên bố production readiness.

## Tiếp theo

Hy thử adapter JSON, đo trên Android và xác nhận budgets. Khiêm kiểm hash/contract,
parity và invalid-input behavior. Nhóm review chất lượng trước khi quyết định có
nghiên cứu tiếp hay giữ Teacher. Official Test chỉ dùng ở mốc cuối đã thống nhất,
không dùng để cứu một candidate yếu.

## Verification

- 81 related tests passed (Student, Teacher release, stacking); four pandas deprecation warnings.
- All code cells in notebooks/07_student.ipynb executed successfully.
- JSON/sklearn parity: 1,585 Validation inputs per candidate; labels equal, max score error < 4e-16.
- CLI inference: five static example URLs passed.
- Producer source revision and hashes are recorded in artifacts/student_week7/manifest.json.
- Android integration, device measurements and independent final evaluation remain pending.
- Fresh local clone with core.autocrlf=true: all 23 source/input/output hashes matched; five CLI examples passed without data/interim files.
