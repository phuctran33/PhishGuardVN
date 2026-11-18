> Bàn giao lịch sử của khảo sát 5 họ. Phần nhóm yêu cầu bổ sung hiện tại là [LightGBM handoff](week7_lightgbm_handoff.md); Teacher stacking vẫn là engine tích hợp chính. Notebook duy nhất: 07_student.ipynb.

# Bàn giao nghiên cứu Student mở rộng — chưa thay Teacher

**Candidate nghiên cứu:** e2_hist__kd_mixed, seed 42 (cố định trước).
**Bản nghiên cứu để review, chưa promote thành model mặc định.**
Đọc notebook 07_student.ipynb và reports/week7_student_comparison.md trước.

## Phúc đã làm gì?

5 họ × 2 cách học × 3 seed = 30 fits. Model được chọn theo mean Validation AP trong
budget 1 MiB dữ liệu model/assets. E2 HistGB KD: AP 0,4370; Teacher 0,5549;
text LR KD baseline 0,3046. Student mới bắt 10/24 phishing, Teacher 15/24 ở ngưỡng riêng.
KD chỉ tăng 0,0048 AP so với HistGB hard-only; bootstrap CI chứa 0.
Không có bằng chứng đủ để đổi engine mặc định hoặc kết luận KD chắc chắn thành công.

## Cho Hy

- Model: artifacts/student_comparison/e2_hist__kd_mixed.json.
- Model JSON 176.786 bytes; cộng PSL + reference = 262.825 bytes.
  Không phải APK/RAM. Chưa có số đo Android.
- Input: 20 E2 theo đúng feature_order trong JSON, tính từ **raw URL** bằng extractor đã freeze.
  Khác Student text LR cũ: không cần TF-IDF vocabulary nhưng cần E2 extractor/reference.
- Cách tính: baseline + tổng giá trị lá 150 cây rồi sigmoid, so score >= threshold.
  Giá trị lá đã chứa learning-rate shrinkage, **không nhân learning_rate thêm lần nữa**.
- Threshold: 0,5232072223928239; đã chọn trên Validation, không dùng lại threshold Teacher.
- Python reference: E2Student.score_features() và predict_one() trong student_comparison.py.
- Ví dụ: python scripts/predict_student_comparison.py --examples.
- Dữ liệu cây dùng numeric feature indices và điều kiện <=, CPython 3.11 reference.
  Không thay entropy/E2 để port; phải kiểm chứng Python–Dart từ input đến score/label.
- Cần Hy xác nhận device/API range, RAM, latency, asset-loading và invalid-input contract.
- E2 LR KD là đối án nhỏ hơn (~85,9 KiB package), cùng Recall/FPR trên Validation,
  nhưng AP thấp hơn. Không tự đổi lựa chọn mà chưa ghi rõ thay đổi tiêu chí.

## Cho Khiêm

- Tests: python -m pytest tests/test_student_comparison.py -q.
- Manifest kiểm hash inference source, reference/PSL, model JSON và mọi bảng kết quả.
- JSON/sklearn parity đã kiểm 1.585 Validation inputs cho từng model seed 42;
  đây chưa phải Android parity. Kiểm lại input/feature order, dtype routing và threshold.
- Extra Trees route bằng float32 như sklearn; HistGB route bằng float64.
- predictions.csv.gz có ID, ground truth, seed, score, prediction; không có raw URL.
- Chưa có app/adapter mới để nghiệm thu offline, không ghi các bước đó là passed.

## Cho Hưng / báo cáo

summary.csv và runs.csv tách mean/SD qua seed với kết quả từng seed/operating point.
paired_bootstrap.csv là uncertainty có điều kiện, không điều chỉnh selection.
Validation tái sử dụng, chỉ 24 positives; không viết như independent final test.
source_label_counts.csv vẫn cho thấy confounding; không có kết luận hết source bias.
Mọi bản yếu đều giữ trong bảng, không che Extra Trees/MLP seed thấp.
Teacher artifacts và original Student baseline giữ nguyên. Notebook 07 đã được gộp baseline/so sánh/LightGBM theo yêu cầu Phúc.
