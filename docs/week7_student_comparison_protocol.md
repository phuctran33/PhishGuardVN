# Student tuần 7 — nghiên cứu so sánh mở rộng

Căn cứ: yêu cầu mở rộng của Phúc sau baseline LR, trên nhánh phuc-week7-student.
[Plan máy đọc](../configs/week7_student_comparison.json) được chốt trước fitting.
Protocol KD tuần 6 không áp dụng; Teacher v2 và original Student artifacts giữ nguyên.
Đây là nghiên cứu trên Validation để chọn candidate, không phải final Test.

## Câu hỏi và giả thuyết

| Họ | Input | Giả thuyết cần kiểm tra |
|---|---|---|
| text_lr | TF-IDF ký tự 8.192 | Mốc lexical hiện có, chạy lại trong cùng điều kiện. |
| e2_lr | 20 E2, StandardScaler | Kiểm tra đổi đầu vào có giúp không, trước khi kết luận do thuật toán. |
| e2_mlp | 20 E2, StandardScaler | MLP 32–16 học tương tác phi tuyến, vẫn nhỏ và phép toán dễ port. |
| e2_hist | 20 E2 | Boosting 150 cây, tối đa 7 lá/cây, học điều kiện tương tác với budget nhỏ hơn nhánh Teacher. |
| e2_extra | 20 E2 | 64 cây ngẫu nhiên sâu tối đa 8, kiểm tra inductive bias khác boosting. |

MLP/HistGB/Extra Trees đều là mô hình mới fit cho thí nghiệm Student, không phải đổi tên
hoặc trích nhánh Teacher đã fit. Không train lại Teacher. Không thêm dependency neural lớn
để thử CNN trong đợt hữu hạn này. Không suy luận CNN kém hơn vì chưa thử.

## So sánh công bằng

Mỗi họ chạy hard_only và kd_mixed, trên seeds 42/43/44.
KD dùng q=0,5*y+0,5*Teacher raw score; hard-only dùng q=y.
Dùng hai bản sao trọng số q/1-q như baseline: tổng trọng số mỗi mẫu vẫn là 1.
Các thuật toán có loss/regularization/optimization khác nhau; không gọi chúng là cùng
compute budget. Báo fit time và thông số để nhìn thấy khác biệt.

Train 13.078 và Validation 1.585 giữ nguyên. Teacher targets cache theo ID đã hash;
targets in-sample, không OOF/cross-fit; Teacher scores Validation chỉ dùng đối chiếu.
Vocabulary, StandardScaler chỉ fit Train. E2/reference không học lại hoặc chỉnh công thức.
Không dùng source/nhãn/ID làm features. Không đọc/chấm Official Test hoặc external.

So KD–hard trong từng họ để đánh giá KD. So text_lr–e2_lr để nhìn tác dụng đổi input.
So e2_lr–MLP/HistGB/Extra cùng E2 để nhìn tác dụng kiến trúc.
Không quy toàn bộ chênh lệch text_lr–HistGB thành lợi ích của distillation.

## Ngân sách đã chốt

Đúng 5 họ × 2 modes × 3 seeds = 30 fits, không grid.
MLP chạy cố định 200 epochs, không random early-stopping split; warning đạt max_iter
được lưu và mô tả là fixed-budget, không tuyên bố optimizer đã hội tụ.
HistGB early_stopping=False nhất quán, 150 vòng, không auto theo số hàng.
Không mở thêm cấu hình sau khi xem kết quả. Cấu hình nhỏ chưa đại diện optimum của cả họ.

## Cách chọn

1. Ngân sách nghiên cứu: model JSON + assets dữ liệu bắt buộc <= 1 MiB.
   PSL tính cho mọi model vì validation/parser dùng nó; E2 tính thêm reference 45 brand.
   Không tính source code, runtime libraries, APK overhead vào số này.
   Đây chưa phải budget thiết bị được Hy xác nhận.
2. Trong các bản đạt budget, xếp mean Validation AP qua 3 seed giảm dần.
3. Nếu mean AP bằng nhau: mean Recall tại FPR budget 1% cao hơn, rồi package nhỏ hơn,
   rồi tên candidate. Không chọn seed tốt nhất: artifact luôn là seed 42.
4. Báo thêm SD (dao động training seed), F1, FPR, agreement, fixed threshold 0,5 và
   desktop p50/p95. Latency đo cùng CPU/runtime, 50 warm-ups + 250 URLs giống nhau.
5. Tách candidate nghiên cứu khỏi Go/No-Go thay Teacher: chưa có Android parity/benchmark
   và independent evaluation thì chưa đổi engine mặc định.

Mean/SD trên 3 seed không phải 3 tập kiểm tra độc lập. Không dùng số seed để làm tăng
cỡ mẫu 24 phishing Validation. Paired domain bootstrap 1.000 lần ước lượng chênh lệch
mean seed AP có điều kiện trên models đã fit; không bao gồm selection uncertainty.
Không coi CI sau khi chọn winner là kiểm định xác nhận độc lập.

## Giới hạn và trạng thái

Validation đã được dùng trong tuần trước và baseline LR; mở rộng họ theo yêu cầu người dùng
là adaptive development. Kết luận chỉ là tốt nhất trong menu/budget đã thử.
Domain disjoint không chứng minh hết near-duplicate, source bias hay chất lượng ngoài dataset.
Source × label vẫn confounded; không đổi nhãn hoặc dataset để nâng metrics.

Artifacts, dự đoán theo ID và mọi kết quả yếu đều lưu cùng nghiên cứu mới.
Không ghi đè artifacts/student_week7, reports/tables/student_week7 hoặc notebook 07.
Notebook 08 trình bày giả thuyết, bảng, PR/confusion/chi phí và lý do lựa chọn; lưu output thật.

## Chạy và đọc code

```powershell
python scripts/compare_students.py
python scripts/summarize_student_comparison.py
python scripts/predict_student_comparison.py --examples
python -m pytest tests/test_student_comparison.py -q
```

Đọc scripts/compare_students.py: main() theo thứ tự chuẩn bị dữ liệu, ma trận input,
vòng family/mode/seed, fit trực tiếp, export/parity, tổng hợp/selection và bootstrap.
src/phishguard_vn/student_comparison.py là predictor JSON, không train hoặc chọn model.

Nguồn thuật toán:
- https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPClassifier.html
- https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html
- https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.ExtraTreesClassifier.html
