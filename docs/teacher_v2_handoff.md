# Bàn giao Teacher v2 candidate — chưa promoted

Teacher v1 vẫn là mặc định. Nhánh nghiên cứu `phuc-teacher-v2-stacking` phụ thuộc PR #24 còn mở.
Đọc [báo cáo](../reports/teacher_v2_stacking.md) trước khi quyết định promotion.

## Chạy thử offline

Dùng môi trường có đúng versions trong `configs/teacher_v2_candidate_lock.json`
(sklearn1.9.1 và các runtime versions đã ghi). Môi trường local hiện tại đã có đủ.

```powershell
python scripts/predict_stacking_candidate.py --examples
python scripts/predict_stacking_candidate.py "example.com" "https://EXAMPLE.com/A?Q=%2F"
```

```python
from phishguard_vn.stacking_candidate import load_candidate
candidate = load_candidate(".")
candidate.predict_one("example.com")
candidate.predict_batch(["example.com", "https://example.com/A"])
```

Không truy cập website. Nhãn 0=benign/1=phishing; score LR chưa calibrated.
Ngưỡng 0.6945740700635259, nhãn theo score >= threshold. Đây là candidate nghiên cứu.

## Đọc code theo flow

1. `scripts/predict_stacking_candidate.py`: đọc URL từ CLI và gọi adapter.
2. `src/phishguard_vn/stacking_candidate.py`: kiểm hash/protocol/versions/reference/feature order,
   kiểm input rồi gọi model đã học; không train.
3. `src/phishguard_vn/stacking.py`: các khối nhỏ, gồm canonical_url(), raw_frame(),
   make_base(), FittedStack.base_scores()/predict_proba(), choose_threshold().
4. `scripts/run_stacking.py`: benchmark đã đăng ký. Đọc main() → run_outer() → select()
   → fit_spec(). fit_spec() của stacking lấy base group OOF từ base_data() rồi fit meta LR.
   fitting_oof() chọn ngưỡng chỉ từ outer-fitting.
5. `scripts/package_stacking_candidate.py`: chỉ fit tổ hợp hai nhánh cuối.
   candidate_base() đặt HistGB early_stopping=False; fit_candidate() tự hiện vòng group crossfit;
   select_candidate() chọn meta params trên full Train. Sau freeze/parity mới đọc Validation/external.
6. `scripts/summarize_stacking.py --audit-only`: đọc lại CSV, kiểm provenance/ID/groups/metrics,
   cập nhật 12 error notes và verification; không refit benchmark.
7. `scripts/check_stacking_supplements.py`: chứng minh CV auto không bật,
   kiểm hostname-only stress và bảng source × label.

Các file tables đều là đầu ra tự sinh; không cần đọc hay chỉnh tay từng file để hiểu model.
Cache/base/outer models dùng nghiên cứu ở data/interim/stacking được ignore; chỉ bundle candidate cuối lên Git.

## Inference cần những gì?

- `models/teacher_v2_candidate.joblib`: fitted SVM/HistGB/meta, vectorizer/IDF/scaler, reference snapshot.
- `configs/teacher_v2_candidate_lock.json`: version, threshold, label mapping, feature order, hashes.
- Runtime: stacking.py, stacking_candidate.py, features.py, brand_features.py, url_parser.py và __init__.py.
- Thư viện base trong pyproject, đúng runtime versions của lock; không cần LightGBM/Torch khi gọi candidate.
- Không cần dataset, report, research tokenizer hay file reference CSV riêng.

Source/contract/reference sai thì loader báo lỗi, không trả benign giả. Không load joblib từ nguồn không tin cậy.

## Cho Hưng, Hy và Khiêm

- Hưng: summary.csv, paired_bootstrap.csv, stress.csv, source_label.csv, audit.json;
  candidate/error_cases.csv và evaluation.json. Kết luận AP chưa thắng chắc, source bias còn.
- Hy: runtime input là raw URL; E2 vẫn lấy từ raw, text canonical bỏ userinfo/fragment.
  Bundle khoảng2,03MiB, chưa có KD/ONNX/Android parity/latency.
- Khiêm: tests/test_stacking.py và CLI trên; fixtures không train project data hoặc truy cập URL.
  Portable thật và 13.078-input parity đã ghi trong metadata.json/verification.json.

Group CV tách domain chưa chứng minh hết source bias. External lịch sử bỏ sót55/92 phishing,
chỉ7 benign nên không tuyên bố sẵn sàng sử dụng bảo mật thực tế.
