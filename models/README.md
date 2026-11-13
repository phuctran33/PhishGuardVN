> Current Teacher: **tfidf_linear_svm C=0.5**, raw char 3-5. See [text_teacher_handoff.md](../docs/text_teacher_handoff.md). The pending/MLP notes below describe historical benchmark stages.

# Model local

Notebook E2 ablation tạo `week5_e1_ablation.joblib` và `week5_e2_ablation.joblib`, mỗi bundle chứa năm model full Train,
feature order/set, selected_model, score_kinds/protocol. E2 có reference snapshot và extractor source hashes.
Shortlist là E2 MLP / HistGB; model full Train dùng cho inference/Validation, không phải Teacher OOF cho KD.

```powershell
.\.venv\Scripts\python.exe scripts/predict_week5.py https://example.com/a --feature-set E2 --model mlp
```

Web/API có thể load một lần và gọi `phishguard_vn.prediction.predict_url`. SVM trả margin, không phải xác suất.
Joblib cần môi trường/code tương thích; không chạy trực tiếp offline trên mobile.

`week5_readable_models.joblib` từ notebook 05 v2; CLI mặc định vẫn dùng file này.
`week4_lr_baseline.joblib` và `week5_lexical_models.joblib` giữ đối chiếu, không bị ablation ghi đè.
Model giữ local và bị Git bỏ qua. Ba bảng OOF/Validation/partitions dạng `.csv.gz` trong `reports/tables/` được đưa vào repo để Hưng audit; không đóng gói bản sao model/code/reference.
Đọc `reports/week5_ablation.md`, `reports/week5_teacher_cards.md`, `docs/week5_phuc_handoff.md`.

## Week 6: Teacher decision pending

week6_teacher_v1.joblib remains the historical MLP artifact from commit 19ceb7b. The expanded comparison has not finalized a Teacher. configs/week6_teacher_lock.json is pending and predict_teacher.py intentionally blocks use as a newly approved Teacher.

Comparison candidates are saved only under ignored data/interim for local review. See reports/week6_teacher.md and docs/week6_phuc_handoff.md; publish the final inference bundle after the team agrees on E2 versus raw-URL input.

## Separate stacking candidate

`teacher_v2_candidate.joblib` is an unpromoted SVM/HistGB/meta-LR bundle including the frozen reference.
Use `configs/teacher_v2_candidate_lock.json` and `scripts/predict_stacking_candidate.py`; the v1 CLI stays unchanged.
See [candidate handoff](../docs/teacher_v2_handoff.md). File size is not peak RAM or Android readiness.
