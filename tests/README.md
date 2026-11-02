# Kiểm thử local

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

- test_splits.py: ID/domain/folds và handoff thật; integration case SKIP nếu chưa tạo handoff.
- test_baseline.py: E1 metrics/leakage/save-load/notes.
- test_readable_ml.py: chạy chính các code cell của notebook v2 trên fixture nhỏ; scaler/search không nhìn outer holdout, validation/test không chọn model, đổi đáp án outer fold không đổi dự đoánfold đó, score SVM margin và CLI Windows/save-load.
- test_experiments.py,test_week5_reporting.py: giữ kiểm chứng tuyến v1 nâng cao đã lưu; không phải nội dung cần đọc trước notebook v2.

Lần kiểm tra 02/11/2026: **111 passed**. Warning còn lại là `registered_domain` deprecated trong parser E1 hiện tại; PR Hy đã có thay thuộc tính nhưng chưa merge vào nhánh này.

Tests bảo vệ tính đúng code/giao thức, không chứng minh chất lượng ngoài dataset. Xem reports/week5_readable.md để đọc kết quả/giới hạn.
