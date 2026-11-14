# Tuần 5 — Phúc: so sánh E1/E2 và shortlist Teacher

Thực hiện 04/11/2026 trên nhánh `phuc-week5-models`, tích hợp main `0054a1b` (Hy PR #5).
**Đã chạy thí nghiệm thật, E2 PRELIMINARY.** Reference có 37 brand đều draft, thiếu ngày truy cập nguồn;
không gọi đây là freeze E2 v1, chưa làm KD, chưa có kết luận đánh giá cuối.

## Đọc code theo thứ tự nào?

1. Học mô hình cơ bản: [notebook 05](../notebooks/05_advanced_models.ipynb), phần 2 → 3 → 4.
2. So sánh brand: [notebook E2 ablation](../notebooks/05_e2_ablation.ipynb), đọc từ trên xuống: ghép ID → khai báo model → partitions → fit/predict OOF → delta → fit Train/Validation → errors → lưu.
3. `scripts/train_week5.py --ablation` chỉ mở/chạy notebook E2 ablation bằng đúng Python đang gọi; code huấn luyện nằm ngay notebook.
4. `src/phishguard_vn/prediction.py` chỉ URL → extractor → model đã lưu; không train lại khi dự đoán.

Giữ notebook 05/kết quả E1 cũ. Notebook E2 ablation chạy lại đối chứng E1 để bảo đảm cùng điều kiện với E2;
metrics E1 khớp các bảng v2 đã lưu trong sai số 1e-10.

## Dữ liệu và phép so sánh công bằng

- Train **13.078** (2.074 phishing, 11.004 benign), Validation **1.585** (24 phishing, 1.561 benign).
- E1 = 12 lexical; E2 = đúng 12 lexical đó + 8 brand. Cùng ID, nhãn, domain và ba folds của Hưng.
- Hai URL Train lỗi parser loại như E1. Không lấy giao mẫu để giấu lỗi ghép; ID/schema/finite/parity sai thì dừng.
- 2 inner StratifiedGroupKFold chỉ trong fitting partition chọn grid bằng AP. Scaler trong pipeline;
  MLP/HistGB tắt early stopping. LR thường/balanced cố định C=1; ba họ còn lại mỗi họ hai cấu hình, như notebook 05.
- AP = `average_precision_score`. Lựa chọn dùng **mean outer-fold AP**, không dùng AP của OOF gộp.
- SVM: ranking score = `decision_function`, nhãn = `.predict()`, ranh giới mặc định 0. Không calibration, không sigmoid.
  LR/MLP/HistGB: score = probability lớp 1, `.predict()` với quy tắc mặc định 0,5. Không tune threshold.
- Reference/tokens/ngưỡng typo không đổi vì nhìn kết quả mô hình. Không thêm selector/E3.
- Test không được train/tune/predict/đánh giá. File E1/core cũ chứa Test được lọc trước bước mô hình;
  extractor E2 dùng `--partition trainval`. Ba bảng bàn giao chỉ có Train/Validation.

## Kết quả Group CV

Tất cả các số dưới là trung bình ba folds; FPR tính trên benign. Mũi tên là E1 → E2.

| Model | AP | Delta AP | F1 phishing | FPR |
| --- | --- | --- | --- | --- |
| logistic_regression | 0.5942 → 0.6417 | +0.0475 | 0.4500 → 0.4944 | 2.30% → 2.27% |
| logistic_regression_balanced | 0.5577 → 0.6306 | +0.0729 | 0.4831 → 0.5439 | 28.94% → 18.28% |
| svm_rbf | 0.6426 → 0.6545 | +0.0118 | 0.5596 → 0.5961 | 1.45% → 1.55% |
| mlp | 0.6992 → 0.7335 | +0.0343 | 0.5989 → 0.6315 | 2.32% → 1.76% |
| hist_gradient_boosting | 0.6979 → 0.7224 | +0.0245 | 0.6066 → 0.6272 | 2.01% → 1.92% |

E2 tăng AP ở cả ba folds của từng cấu hình. Với MLP, delta AP là +0,0169 / +0,0271 / +0,0588
(mean +0,0343; std 0,0219). HistGB: +0,0191 / +0,0230 / +0,0314 (mean +0,0245; std 0,0063).
FPR MLP giảm cả ba folds; FPR HistGB tăng khoảng 0,027 điểm phần trăm ở folds 0 và 2, giảm 0,327 điểm ở fold 1.
Vì thế không nói HistGB giảm FPR ở mọi fold. LR balanced giảm FPR mạnh nhưng vẫn khoảng 18,28%, không phù hợp để cảnh báo chỉ vì Recall cao.
SVM tăng AP/F1 nhưng mean FPR tăng 1,45% → 1,55%.

Bảng [paired folds](tables/06_paired_folds.csv) và [delta mean/std/min/max](tables/06_deltas.csv)
giữ đầy đủ kết quả. Đây là **uncertainty mô tả**, không phải confidence interval hay kiểm định ý nghĩa thống kê:
chỉ ba folds có training chồng lấp, một seed, một dataset và có lựa chọn giữa nhiều cấu hình.
Không có bootstrap nhiều lớp hay kết luận “chắc chắn tổng quát hóa”.

## Brand giúp ở đâu, còn rủi ro gì?

Có **578/13.078 = 4,42%** URL Train bật ít nhất một brand feature (342 phishing, 236 benign).
`brand_in_path` hằng 0 được giữ đúng schema; không bỏ theo thống kê Validation/Test.
So sánh subgroup chỉ mô tả: nhóm có brand vốn khác tỷ lệ nhãn với nhóm còn lại; không so AP của hai subgroup như cùng phân phối.

- MLP trên nhóm có brand: TP 225 → 315, FN 117 → 27; đồng thời FP 2 → 14. Trên nhóm không có brand,
  FP 253 → 180 nhưng FN 959 → 1.000. Lợi ích không đồng đều.
- HistGB trên nhóm có brand: TP 224 → 294, FN 118 → 48; FP 3 → 19. Trên nhóm không có brand,
  FP 218 → 192, FN 956 → 981.
- Tất cả OOF: MLP FP 255 → 194, FN 1.076 → 1.027; HistGB FP 221 → 211, FN 1.074 → 1.029.
  MLP sửa đúng 209 mẫu trước sai nhưng làm sai thêm 99; HistGB tương ứng 111 và 56.

Đây là contribution của **cả nhóm** brand cộng quy trình refit/tune trên Train. Với MLP, kiến trúc tốt nhất
cũng thay đổi giữa E1/E2 nên không quy toàn bộ delta cho một feature riêng. Không coi coefficient/feature flag là giải thích nhân quả.

Một số mẫu thật trong [bảng ví dụ](tables/06_error_examples.csv), trải cả ba folds và hai hướng thay đổi:

| URL đã vô hiệu hóa | Dữ kiện quan sát | Giả thuyết và kiểm tra tiếp |
| --- | --- | --- |
| `quatangshopeevn[.]com` (fold 1) | Dataset phishing; MLP/HistGB từ FN → TP; brand_in_domain=1, mismatch=1 | Tín hiệu brand có thể giúp; Hưng đối chiếu OOF/feature, không khẳng định chỉ mismatch gây thay đổi |
| `nganhangagribank[.]vn` (fold 2) | Dataset phishing; MLP FN → TP; domain brand/mismatch bật | Hy kiểm tra rule/reference; đây là nhãn dataset, chưa kiểm chứng website hiện tại |
| `vnpayment[.]vn` (fold 1) | Dataset benign; cả hai từ TN → FP; brand/mismatch=1, susp_token_cnt=1 | Có thể false match hoặc thiếu reference; cần Hy xem explain_brand_matches, không tự thêm whitelist theo nhãn |
| `vaynganhang24hbldv[.]com` (fold 2) | Dataset phishing; cả hai TP → FN; cả tám brand features bằng 0 | Reference/rule có thể không bao phủ, hoặc thay đổi ranh giới; không sửa feature chỉ để bắt riêng ca này |
| `https://www[.]binhthuan[.]dcs[.]vn` (fold 1) | Dataset benign; MLP FP → TN; tám brand features đều 0 | Ví dụ refit có thể đổi ranh giới ngay khi mẫu không bật brand; không kể thành phát hiện brand trực tiếp |

24 dòng ví dụ là cặp mẫu–model được chọn để đọc, có URL lặp giữa hai model; không phải 24 mẫu ngẫu nhiên/độc lập.
Notes trong CSV là phân tích tự động, không gán là human review của Hưng. Bàn giao toàn bộ OOF để Hưng tự lấy mẫu thêm.

## Validation: tín hiệu cần thận trọng

Validation có chỉ **24 phishing**, tỷ lệ 1,51%, khác Train 15,86%. Source–label confounding từ dataset vẫn còn.

| Model | AP E1 → E2 | F1 E1 → E2 | FP E1 → E2 | FN E1 → E2 |
| --- | --- | --- | --- | --- |
| MLP | 0,4314 → 0,3762 | 0,3288 → 0,3824 | 37 → 31 | 12 → 11 |
| HistGB | 0,4338 → 0,4278 | 0,4063 → 0,4590 | 27 → 23 | 11 → 10 |

F1 tăng tại ngưỡng mặc định **không có nghĩa AP phải tăng**: AP đo thứ hạng trên toàn dải score.
Cả hai AP Validation đều giảm, MLP giảm khoảng 0,0551. Thay tỷ lệ nhãn có thể ảnh hưởng precision/AP;
khác domain/source/brand coverage cũng là giả thuyết, không khẳng định nguyên nhân chỉ là imbalance.
Validation ít positive nên chưa đủ chứng cứ chọn ngược lại model; không tune model/threshold/reference theo bảng này.
Cần Hưng xác nhận mô hình lỗi/shift và đánh giá Test một lần sau khi chốt protocol/model; không tự mở Test bây giờ.

## Shortlist và phần kế hoạch đã làm

Shortlist đúng quy tắc Train-only ghi trước khi chạy: **E2 MLP** và **E2 HistGB**.
Đọc [Teacher cards](week5_teacher_cards.md) để xem cấu hình, trade-off, kích thước và latency PC.
MLP xếp đầu theo AP; chưa gọi là Teacher cuối cùng/đã sẵn sàng production, Recall CV mới khoảng 50%.

| Task Phúc | Trạng thái |
| --- | --- |
| P5.1 E1 release lock | Giữ nguyên kết quả/snapshot E1; merged code parser alias của Hy cho metrics E1 v2 tái lập |
| P5.2 Model comparison | Đã có LR thường/balanced, RBF SVM, MLP, HistGB trên 12 features |
| P5.3 E2 ablation | Đã chạy 20 features, matched samples/folds, delta AP/F1/FPR và độ ổn định mô tả; bản v0 sơ bộ |
| P5.4 Teacher shortlist | Đã chọn tối đa hai họ bằng Train CV; lưu model/cards/PC latency; không thực hiện KD |
| P5.5 Evaluation & handoff | OOF/Validation/partitions dạng CSV nén đã tạo trong reports/tables; Hưng còn audit độc lập/xác nhận kết luận; Test chưa chấm |

Cách chạy/bàn giao: [docs/week5_phuc_handoff.md](../docs/week5_phuc_handoff.md).
Kiểm chứng: [week5_validation.md](week5_validation.md). Nhánh làm việc: `phuc-week5-models`; Hưng còn audit/xác nhận kết luận qua review PR.
