> Cập nhật: baseline được giữ để đối chiếu, toàn bộ thí nghiệm nằm trong notebook 07_student.ipynb. Đọc [LightGBM handoff](week7_lightgbm_handoff.md) cho candidate bổ sung; Teacher vẫn là engine chính.

> Bàn giao baseline lịch sử. Candidate nghiên cứu mới nằm trong [bàn giao so sánh mở rộng](week7_student_comparison_handoff.md); CLI/artifacts bên dưới vẫn dành cho baseline cũ.

# Bàn giao Student tuần 7 — bản nghiên cứu ban đầu

Nhánh: phuc-week7-student. Căn cứ: week7_student_offline_plan.md.
Đọc [protocol và flow](week7_student_protocol.md), rồi [kết quả](../reports/week7_student.md).

## Cho Hy

- Model thử trước: artifacts/student_week7/kd_mixed.json.
- Bản đối chiếu: artifacts/student_week7/hard_only.json.
- Manifest: artifacts/student_week7/manifest.json; gồm SHA-256, model version,
  threshold từng bản, nguồn Teacher và trạng thái experimental.
- Examples: artifacts/student_week7/examples.json, toàn bộ URL là ví dụ tổng hợp.
- Python reference:
  `python scripts/predict_student.py --examples`
  hoặc `python scripts/predict_student.py --candidate hard_only example.com`.
- Không load Teacher khi Student inference. Không cần Train để chạy predict.
- Đây là JSON để thử port Dart, **chưa phải model đã chạy trên Android**.
- Cần thống nhất device/API range, size/RAM/latency budget trước khi chấp nhận.
  Chưa chuyển Student thành mặc định; Teacher v2 vẫn là engine chính.

Model JSON gồm terms (thứ tự cột), idf, coef, intercept, ngram_range, threshold
và normalization contract. Thuật toán tham chiếu nằm ở Student.score_one().
Giữ Unicode code points, normalization và sublinear TF/L2 như protocol.
Output gồm label/class_id, score chưa calibrated, threshold, model_version
và trạng thái experimental; không hiện thành phần trăm an toàn.

## Cho Khiêm

Chạy `python -m pytest tests/test_student.py -q`.
Tests không train dữ liệu đồ án; chỉ fit fixtures nhỏ và đối chiếu artifact thật.
Đã có guards cho targets sai, overlap domain, model bị sửa, input lỗi,
threshold với tied scores, và JSON–sklearn parity.
Dự đoán Validation và confusion counts có trong reports/tables/student_week7/.
Android parity/offline QA cần adapter từ Hy, chưa có bằng chứng ở nhánh này.

## Cho Hưng

Bảng benchmark.csv có hai operating points; không trộn các hàng.
teacher_validation.json dùng ngưỡng Teacher đã khóa, còn Student chọn ngưỡng bằng Validation.
Validation được dùng chọn Student nên chưa phải phép so sánh final test độc lập.
AP tăng nhẹ từ hard_only sang KD không đủ kết luận KD thành công; chất lượng thấp hơn Teacher.
source_label_counts.csv cho thấy source–label confounding còn nguyên.
Không cần gửi file riêng: artifacts, targets và các bảng review đều đi cùng repo.
