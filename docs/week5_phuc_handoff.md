# Phúc bàn giao E1–E2 cho Hưng — tuần 5

Sau khi Phúc commit/push và Hưng pull nhánh chứa thay đổi, Hưng đọc trực tiếp ba file trong `reports/tables/`; **không cần nhận riêng, giải nén hay train lại trước khi audit**.

| File | Nội dung |
| --- | --- |
| [06_oof_predictions.csv.gz](../reports/tables/06_oof_predictions.csv.gz) | 130.780 dòng = 13.078 Train IDs × 10 candidates (E1/E2 × 5 cấu hình), mỗi candidate/ID đúng một dòng |
| [06_validation_predictions.csv.gz](../reports/tables/06_validation_predictions.csv.gz) | 15.850 dòng = 1.585 Validation IDs × 10 candidates; chỉ báo cáo bổ sung |
| [06_training_partitions.csv.gz](../reports/tables/06_training_partitions.csv.gz) | Context 0/1/2/full_train; mẫu fitting/held_out và inner_fold_id, dùng chung E1/E2 |

## Đọc và kiểm tra

Chạy từ root repo:

```python
import pandas as pd

oof = pd.read_csv("reports/tables/06_oof_predictions.csv.gz")
validation = pd.read_csv("reports/tables/06_validation_predictions.csv.gz")
partitions = pd.read_csv("reports/tables/06_training_partitions.csv.gz")
```

- `candidate` ví dụ `E2__mlp`; nhãn `true_label`/`predicted_label`: 0=benign, 1=phishing.
- OOF có `evaluation_partition=group_cv`, `fold_id=0/1/2`; Validation là `official_validation`, không có fold_id.
- SVM: `score_kind=decision_function`, score là margin, ranh giới mặc định **0**. Không ép về [0,1] hay dùng ngưỡng 0,5.
- LR/MLP/HistGB: score là probability lớp 1, ngưỡng mặc định **0,5**. Mọi nhãn lấy từ `estimator.predict`; không calibration/threshold tuning.
- Context k: học trên role=fitting, chấm role=held_out. Với inner fold j, chỉ học trên fitting có inner_fold_id≠j, chấm fitting có inner_fold_id=j. Scaler ở trong pipeline.
- `full_train` chỉ fit model cuối cho inference/Validation, không tạo OOF hoặc soft targets để chấm lại Train.

Hưng đối chiếu ID/nhãn/domain/folds với handoff tuần 4 và X E2 native của Hy; kiểm tra E1/E2 cùng mẫu, inner/outer domains disjoint, không có Validation/Test trong fitting. Sau đó tính lại AP/P/R/F1/FPR/confusion theo fold và xác nhận kết luận.
AP chọn model là **mean theo ba folds**, không phải pooled AP. Tham số ở [06_parameters.csv](../reports/tables/06_parameters.csv);
feature order, reference/version, input/file hashes, provenance và phiên bản thư viện ở [metadata](../reports/tables/06_ablation_metadata.json).
Metadata giữ thời điểm/HEAD thật lúc train; phần ghi chú export giải thích việc đổi sang CSV nén mà không train lại. Hash code gốc lúc train được giữ riêng.

## Kết luận đang chờ Hưng xác nhận

Shortlist Train-only: **E2 MLP** (AP CV 0,6992→0,7335) và **E2 HistGB** (0,6979→0,7224); mean FPR đều giảm.
Nhưng AP Validation của cả hai giảm. Reference `e2-brand-v0` còn **draft**, Test chưa đánh giá, KD chưa làm; kết quả là **sơ bộ**.
Đọc [báo cáo ablation](../reports/week5_ablation.md) để xem delta, FP/FN và giới hạn. Audit độc lập/human review của Hưng vẫn pending.

## Chỉ khi cần tái tạo kết quả/model

Model giữ local trong `models/`; code/reference có sẵn trong repo. Dùng `.venv`, tạo handoff tuần 4 theo **01 → 03 → 02** nếu chưa có, rồi chạy:

```powershell
.\.venv\Scripts\python.exe scripts/05_build_matrix_x_brand.py --partition trainval
.\.venv\Scripts\python.exe scripts/train_week5.py --ablation
```

Notebook [05_e2_ablation.ipynb](../notebooks/05_e2_ablation.ipynb) trực tiếp train và xuất lại ba CSV nén cùng các bảng metrics. Chạy lại sẽ thay kết quả local; không cần làm trước khi review lần chạy đã bàn giao.
