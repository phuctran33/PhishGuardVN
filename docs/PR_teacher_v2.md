## Đã xử lý review: promote stacking thành Teacher v2

Teacher mặc định nay là **canonical TF-IDF + Linear SVM và HistGB E2 → scaled Logistic Regression**.
Không thêm mô hình, không train lại, không đổi threshold, công thức E2, reference, dữ liệu hay bảng benchmark.

### Runtime và regression

- Khóa **CPython 3.11** trong metadata/lock/loader; runtime khác bị chặn trước unpickle/inference, thông báo lỗi rõ.
- Giữ artifact đã freeze (SHA256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`); không sửa entropy để đổi kết quả.
- Tests mô phỏng Python 3.10/3.12/3.13 và metadata thiếu runtime đều bị từ chối.
- Real-bundle regression kiểm đủ 1.585 Validation và 99 external: score khớp CSV với atol=1e-12, nhãn khớp tuyệt đối. Không score Official Test.
- CI cài đúng dependencies từ `requirements-teacher.txt` trên Python 3.11 và chạy regression này.
- Local focused: **80 passed**; full available: **480 passed, 2 skipped**. Skip là research extras không cài trong env này và empty brand regression lịch sử. Research fixtures vẫn chạy ở job CI riêng.

### Promotion và lịch sử

- `configs/teacher_lock.json` là pointer chính thức, kiểm hash runtime lock/artifact/threshold.
- `load_teacher(".")` và `scripts/predict_teacher.py` dùng stacking v2.
- `released_teacher.py` đổi trạng thái/phiên bản output; không đổi weights hoặc tag lịch sử trong pickle.
- V1 bundle/lock giữ nguyên; vẫn load được khi truyền `configs/week6_teacher_lock.json` tường minh.
- Metadata promotion mới: `reports/tables/stacking/promotion.json`; metadata/evaluation candidate cũ giữ lịch sử.
- Hướng dẫn: [teacher_v2_release.md](https://github.com/phuctran33/PhishGuardVN/blob/phuc-teacher-v2-stacking/docs/teacher_v2_release.md).

### Kết quả và giới hạn giữ nguyên

Mean outer AP stacking 0,930667 vs raw SVM 0,925628; CI delta vẫn chứa 0.
External vẫn **bỏ sót 55/92 phishing**, chỉ 7 benign; source bias còn và score chưa calibrated.
Official Test chưa đánh giá. Promotion là quyết định chọn Teacher của nhóm, không phải chứng nhận an toàn thực tế.
Không KD/Android/API integration hoặc tự merge.

PR vẫn phụ thuộc #24 (base nhánh v1). Nhờ nhóm review commit, regression và CI head mới trước merge.
