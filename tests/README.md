# Kiểm thử local

Cài test extra trong .venv: `python -m pip install -e '.[test]'`.
Chạy `python -m pytest -q` tại root repo.

- test_splits.py: domain keys, train-only group CV, độ tái lập và handoff thật.
- test_baseline.py: AP/confusion matrix, scaler fit trong fold, cấm val/test vào folds,
  nối ID, metadata không vào X, model selection độc lập validation, lưu/load và URL lỗi.

Integration test split cần CSV tạo từ notebook 01 → 03 → 02; nếu thiếu sẽ SKIP.
Bộ kiểm thử đã chạy gồm split/CV, baseline, bảo toàn ghi chú, cấu hình và metadata báo cáo.
Test synthetic không chứng minh hiệu năng ngoài dataset; xem reports/week4_baseline.md.
