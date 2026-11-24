# Week 7 — Teacher error analysis và Modeling/Evaluation của Hưng

Ngày 17/11/2026. Phân tích offline từ artifacts có nhãn đã lưu; không chạy benchmark mới, không train/tune hoặc dùng Official Test. Không truy cập URL đích.

Teacher phát hành `teacher-stacking-v2`, protocol `full_train_group_oof_fpr_target_0.01`, threshold `0.6945740700635259` theo release lock. Bundle SHA256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`. CPython 3.11. Các file candidate giữ tên lịch sử; release lock/loader quản lý trạng thái chính thức. Không sửa metadata candidate để đổi provenance.

## HU7.5 — Phạm vi và kết quả

`python scripts/analyze_week7_teacher_errors.py` đối chiếu bundle hash/metadata với release lock, labels theo ID Validation và prediction theo đúng `score >= threshold`. Chỉ đọc split Validation để join các ID đã được đánh giá. Core Validation 1.585 là tập con của file Validation 7.266 dòng; không coi phần còn lại là đã chấm. External chỉ tổng hợp 99 saved predictions hostname lịch sử; không chạy inference lại. Input hashes nằm trong [summary JSON](tables/week7/teacher_error_summary.json).

| Tập | N | Positive / negative | TP | FP | TN | FN |
|---|---:|---:|---:|---:|---:|---:|
| validation | 1585 | 24 / 1561 | 15 | 14 | 1547 | 9 |
| external | 99 | 92 / 7 | 37 | 1 | 6 | 55 |

Validation recall 15/24 = 62,5%; FPR 14/1.561 = 0,8969%, AP 0,55491 theo evaluation đã lưu. External recall 37/92 = 40,22%; FPR 1/7 = 14,29%, AP 0,98134. AP là ranking, khác recall tại operating point; 7 negatives quá ít để diễn giải FPR ổn định. External là exploratory historical host-only, không thay thế đánh giá triển khai độc lập. 167 candidates: 99 có prediction có nhãn, 68 còn ngoài phạm vi chấm.

## Nhóm lỗi có bằng chứng (nhóm chồng lấp)

| Tập / loại lỗi | Tín hiệu quan sát | Số / mẫu số lỗi cùng loại |
|---|---|---:|
| validation / FN | no_reference_signal | 9/9 |
| validation / FP | no_reference_signal | 14/14 |
| external / FN | brand_in_subdomain | 20/55 |
| external / FN | brand_mismatch | 21/55 |
| external / FN | brand_near_match | 1/55 |
| external / FN | historical_host_only | 55/55 |
| external / FN | no_reference_signal | 32/55 |
| external / FP | brand_near_match | 1/1 |
| external / FP | historical_host_only | 1/1 |

Tất cả 23 lỗi Validation không có event reference (kể cả suspicious-token engine); điều này chứng minh giới hạn bao phủ quy tắc, **không chứng minh** nhánh brand là nguyên nhân lỗi. External có 21/55 FN cùng mismatch, 20/55 có brand trong subdomain, 32/55 không có reference event; các nhóm không cộng lại thành tổng. Một FN và FP có near-match. Rules chỉ mô tả chuỗi, không là attribution cho SVM/HistGB/LR.

## Ví dụ vô hiệu hóa liên kết

| ID | Tập / lỗi | URL defanged | Saved score | Quan sát |
|---|---|---|---:|---|
| 0b5a7288-5ea5-5656-9943-c403a90738e1 | validation/FP | `fuguohengxing589629[.]com` | 0.9427241305342355 | tranco · FP theo nhãn artifact và operating point |
| 21fde635-3f3b-5cb2-b59f-84a028e31c27 | validation/FN | `m[.]kone365[.]com` | 0.3561979952568251 | tinnhiemmang · FN theo nhãn artifact và operating point |
| ext_pilot_phishing_0001 | external/FN | `acb[.]chamsoc-the-uudaikhachhang-tructuyen[.]com[.]vn` | 0.5859738662434036 | ACB official list of fake websites · FN theo nhãn artifact và operating point |
| ext_pilot_benign_0011 | external/FP | `www[.]co-opbank[.]vn` | 0.9431756316522734 | vnba_member_directory · FP theo nhãn artifact và operating point |

Bảng bàn giao toàn bộ **79 lỗi** (23 Validation + 56 external), score, observation, hypothesis, next check và evidence engine: [teacher_errors.csv](tables/week7/teacher_errors.csv). `human_verification=not_performed`: đây là phân tích bằng công cụ, không tạo xác nhận người dùng/nhãn website mới.

## Giả thuyết có thể kiểm chứng

1. Host-only mất path/query nên một số FN external thiếu tín hiệu phân biệt. Kiểm bằng artifact paired full-URL/host-only có provenance khi được bàn giao, không tự dựng URL lịch sử hoặc tune external. Hiện `plausible_unverified`.
2. Lexical patterns benign/phishing chồng lấp gây FP tranco và FN feed: kiểm neighbor/token/branch-score của từng ID trong Train và artifacts hiện có. Chưa có per-case causal attribution nên `plausible_unverified`.
3. Coverage 45 brands hạn chế: kiểm tỷ lệ có/không event trong cả TP/TN đối chứng và reference scope trước khi kết luận tương quan. Không tự tăng brands hay thay E2. 21 FN có mismatch chứng tỏ rule hit không bảo đảm model vượt threshold.
4. Source/label bias: Validation positives đều tinnhiemmang (15 TP/9 FN), FP gồm 13 tranco và 1 tranco_vn; external FN tập trung ACB 22/37, NCSC/Dak Lak 24/36, Quảng Ngãi 8/10, Ministry weekly 1/1. Đối chiếu thời điểm/representation/nguồn nhãn trước khi suy rộng; không đổi nhãn hoặc khẳng định website hiện tại độc hại.

## HU7.6 — Vì sao giữ Teacher và tiếp nhận Student

Teacher được chọn bằng Core Train group CV/OOF và có release lock; canonical char TF-IDF/SVM và E2 HistGB bổ sung góc nhìn, LR kết hợp score. Validation đã được quan sát trước đó, chỉ 24 positives; không tuyên bố independent final performance hoặc superiority nhân quả từng nhánh. Score LR chưa hiệu chuẩn; ngưỡng kiểm soát Train OOF FPR 1% không bảo đảm production FPR 1%. Giữ nguyên model/threshold trong Web/API.

Đã đọc handoff/manifest/report/benchmark trên `phuc-week7-student` revision `37581b28b29aa7c78a11db8905ae9636b7e5e5b9` (chưa merge vào phần Web). Benchmark SHA256 `cd6f7f7337bf5d1173829df99f5b641efb85dd61cfe532a5f2685227622314c7` khớp manifest. Không chỉnh Student. Nguồn: `docs/week7_student_handoff.md`, `reports/week7_student.md`, `artifacts/student_week7/manifest.json` tại revision này.

| Student development candidate | Operating point | AP | Recall | FPR | TP / FP / TN / FN | Threshold | JSON bytes |
|---|---|---:|---:|---:|---|---:|---:|
| hard_only | validation_fpr_budget | 0.292578 | 0.333333 | 0.008969 | 8 / 14 / 1547 / 16 | 0.5486056188894293 | 495557 |
| hard_only | fixed_0.5 | 0.292578 | 0.375000 | 0.014094 | 9 / 22 / 1539 / 15 | 0.5 | 495557 |
| kd_mixed | validation_fpr_budget | 0.304568 | 0.333333 | 0.008328 | 8 / 13 / 1548 / 16 | 0.564855787905593 | 495753 |
| kd_mixed | fixed_0.5 | 0.304568 | 0.375000 | 0.014094 | 9 / 22 / 1539 / 15 | 0.5 | 495753 |

Bàn giao đọc tại revision `37581b28b29aa7c78a11db8905ae9636b7e5e5b9` của `phuc-week7-student`; benchmark SHA256 `cd6f7f7337bf5d1173829df99f5b641efb85dd61cfe532a5f2685227622314c7` khớp manifest upstream. [Receipt metrics/provenance](tables/week7/student_handoff_receipt.json). Không merge/copy model Student vào Web/API.

Protocol `week7-student-dev-v1`: Train 13.078, Validation 1.585; 2 Train IDs loại do eligibility. Character TF-IDF 8.192 + LR, hard-only so với mixed KD alpha 0,5. Teacher targets **in-sample**, không phải cross-fitted OOF KD. Validation dùng chọn candidate **và ngưỡng**, nên là development metrics, không đánh giá độc lập. Không so row fixed-0.5 với row FPR-budget mà bỏ qua operating point.

KD AP tăng khoảng 0,012 so hard-only nhưng recall vẫn 8/24; Teacher 15/24. Hard-only agreement 98,55% và MAE 0,06058 tốt hơn KD 98,49%/0,06329. All-benign baseline đã đạt 1.561/1.585 = 98,49% accuracy; agreement cao không đủ chứng minh bảo toàn phát hiện phishing. JSON size không phải RAM/APK và desktop latency không phải device latency.

Kết luận bàn giao Phúc: **NO-GO thay Teacher mặc định**; KD experimental chỉ dành feasibility trial. Manifest `android_verified=false`, chưa có Android/Dart parity/device verification. Producer tree dirty được ghi nguyên trạng upstream, không đổi thành clean. Không phát hành Student hoặc nhận Android sẵn sàng. Hy/Phúc tiếp tục #28/#29; Khiêm #31 phụ trách independent QA/security/clean-clone/integration sau review PR.

Bàn giao Khiêm: `/inspect` schema/errors/fixtures theo docs/api_contract.md; ảnh QR thực và client/widget tests trong apps/web/test; lệnh demo và ảnh browser trong week7_web_verification.md. Review tích hợp của Hưng kiểm API validation, no-network, stale-response, rule/ML separation; không tự approve hoặc merge PR.
