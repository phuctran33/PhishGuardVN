# Kiểm thử local

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test,teacher]'
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

- test_teacher_week6.py: chạy code cell thật của E2 v1; chặn v0, kiểm tra scaler/search chỉ trong fitting, đổi đáp án outer holdout không đổi dự đoán của fold đó, Validation không chọn Teacher.

Week-6 expanded tests cover TF-IDF fitting-only vocabulary, inner-OOF low-FPR thresholds, separate E2/raw rankings and blocked unfinalized inference. Install .[teacher] to run notebook tests; without those optional packages they skip.

Week-6 clean review 2026-11-13: Teacher fixtures 13 passed/0 skipped; full local suite 400 passed/1 skipped (existing empty brand regression parameter set). The four optional-library fixture cases actually fit and reload LightGBM, XGBoost, CatBoost and Balanced RF. These fresh results are separate from the 2026-11-11 historical 396/1 run. CI rejects Teacher skips and reports missing-data integration skips separately.

Research extension: install .[research,test], then python -m pytest tests/test_url_research.py -q -rs (27 passed, no skips). Full research environment: 427 passed, 1 historical empty-parameter skip. The separate research CI job installs CPU torch/tokenizers/transformers and rejects skipped research fixtures; the Teacher-only job may skip this optional module.
