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

## Teacher v1 tuần 6

week6_teacher_v1.joblib là Teacher E2 v1 nhỏ (~44 KB), được cho phép quản lý trong Git để bàn giao. Xem docs/week6_phuc_handoff.md và configs/week6_teacher_lock.json. Dùng scripts/predict_teacher.py --examples; không cần retrain để predict.
