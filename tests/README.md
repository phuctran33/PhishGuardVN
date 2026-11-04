# Kiểm thử local

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

- test_splits.py: ID/domain/folds và handoff thật; integration case SKIP nếu chưa tạo handoff.
- test_baseline.py: E1 metrics/leakage/save-load/notes.
- test_readable_ml.py: chạy chính các code cell của notebook v2 trên fixture nhỏ; scaler/search không nhìn outer holdout, validation/test không chọn model, đổi đáp án outer fold không đổi dự đoánfold đó, score SVM margin và CLI Windows/save-load.
- test_experiments.py,test_week5_reporting.py: giữ kiểm chứng tuyến v1 nâng cao đã lưu; không phải nội dung cần đọc trước notebook v2.

Lần kiểm tra 04/11/2026: **152 passed**, không skip; `pip check` pass. Đã tích hợp parser/brand từ Hy PR #5.

- `test_brand_features.py`: hợp đồng/parser/brand của Hy.
- `test_ablation_ml.py`: chạy code cells notebook E2 ablation; E1/E2 cùng ID/folds, scaler/tuning trong fitting partition, không dùng nhãn Val/Test chọn model, đổi outer answers không đổi dự đoán fold đó; invalid pairing/lexical/schema/Test dừng trước fit; E2 reload/direct-extraction parity và reference snapshot/source drift.

Tests bảo vệ tính đúng code/giao thức, không chứng minh chất lượng ngoài dataset. Xem reports/week5_readable.md để đọc kết quả/giới hạn.
