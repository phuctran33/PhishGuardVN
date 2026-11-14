# Teacher chính thức: stacking v2 — cập nhật sau review

Nhóm chọn canonical TF-IDF + Linear SVM và HistGB E2 → scaled Logistic Regression làm Teacher.
Không thêm model, không train lại, không đổi threshold, E2, reference, dữ liệu hoặc benchmark.

## Runtime bắt buộc

**CPython 3.11**. Bundle được tạo trên 3.11.7. Python 3.12/3.13/3.10 và implementation khác bị từ chối trước unpickle/inference.
Reviewer báo entropy dùng sum() khác giữa 3.11 và 3.12 có thể đổi nhánh cây.
Không sửa công thức entropy để tương thích; giới hạn runtime cho artifact đã freeze.

```powershell
python --version
python -m pip install -e ".[inference]"
python -m pip install -r requirements-teacher.txt
python scripts/predict_teacher.py --examples
```

```python
from phishguard_vn.teacher import load_teacher
teacher = load_teacher(".")  # configs/teacher_lock.json -> stacking v2
teacher.predict_one("example.com")
```

configs/teacher_lock.json là pointer chính thức: hash candidate runtime lock, cùng bundle SHA và threshold đã kiểm.
Artifact vẫn mang tag lịch sử candidate trong pickle; ReleasedTeacher chỉ đổi nhãn phiên bản trả về,
không sửa model/weights hoặc giả rằng bundle được train lại.
configs/teacher_v2_candidate_lock.json bổ sung runtime Python; metadata promotion ở reports/tables/stacking/promotion.json.
Metadata/evaluation candidate cũ là lịch sử, không đổi provenance của những lần chạy trước.

## Giữ lịch sử v1

models/teacher_tfidf_svm_v1.joblib và configs/week6_teacher_lock.json không đổi.
Truyền lock v1 tường minh khi cần tái hiện:
```python
import json
from pathlib import Path
lock = json.loads(Path("configs/week6_teacher_lock.json").read_text(encoding="utf-8"))
old_teacher = load_teacher(".", lock)
```

Không tự fallback v1 khi lock/model mới lỗi. Loader báo lỗi để người dùng sửa runtime/contract.
External evaluator lịch sử vẫn dùng lock được truyền tường minh, không ghi đè kết quả cũ.
Tích hợp API/mobile riêng không nằm trong thay đổi này.

## Kiểm chứng và giới hạn

tests/test_teacher_release.py chặn runtime không hỗ trợ, kiểm default/explicit v1 và đối chiếu score/nhãn của
bundle thật với CSV Validation/external đã freeze (atol=1e-12, labels phải khớp tuyệt đối).
CI cài đúng runtime libraries và chạy các tests này, không train model project hay truy cập website.
Trong test Validation, chỉ join/score 1.585 IDs đã lưu; không score Official Test.

External vẫn bỏ sót **55/92 phishing**, chỉ 7 benign; score LR chưa calibrated.
Source × label còn confounding. Official Test **chưa đánh giá**.
Promotion là quyết định chọn Teacher của nhóm, không phải chứng nhận an toàn sử dụng thực tế.
