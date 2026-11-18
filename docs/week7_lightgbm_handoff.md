# Bàn giao LightGBM Student — research candidate, Teacher vẫn là engine chính

Đọc notebook 07_student.ipynb và báo cáo week7_student_comparison.md.
Chưa push; không tự promote Student. Không cần gửi file riêng khi nhóm được bàn giao repo.

## Kết quả cần hiểu đúng

- Group CV AP: hard=0,9184; KD=0,9186. Pooled-OOF CI của KD−hard chứa 0.
- Teacher fold-CV mean AP≈0,9307, cao hơn Student. Không so con số CV với Validation khác cohort.
- Validation: hard AP=0,6223; KD=0,6549; Teacher AP=0,5549.
  Student 13 TP/10 FP/1551 TN/11 FN; Teacher 15 TP/14 FP/1547 TN/9 FN ở ngưỡng tương ứng.
- Student KD AP cao hơn Teacher ở Validation là kết quả thật được giữ nguyên.
  Chưa có independent final evaluation, Android parity hoặc device benchmark.
- Model + vocabulary/IDF + reference/PSL khoảng 1,19 MiB; chưa gồm runtime/APK overhead.

## Cho Hy — inference contract

Folder artifacts/student_lightgbm/:
- kd_mixed.json và hard_only.json: cây cho JSON/Dart reference.
- *.model.txt: native LightGBM để kiểm chứng/chuyển đổi, không cần đóng gói đồng thời hai định dạng.
- features.json: thứ tự vocabulary, IDF, ngram range, normalization và 20 E2 nối sau.
- brand_reference_v1.csv và PSL: assets dữ liệu cố định.
- manifest.json: hashes, threshold, selected_mode, runtime/source identity và packaging-only supplement.
- python_reference.json: 52 valid + 6 rejected fixtures hiện tại; không phải dataset có nhãn accuracy.

Flow: raw URL → strict validation → canonical text (bỏ scheme/userinfo/fragment,
host IDNA/lowercase, giữ path/query case và escapes) → char 3–5 TF-IDF → nối E2 tính từ raw URL.
N-grams theo Unicode code points, không cắt UTF-16 code units.
TF=1+ln(count), nhân IDF đã lưu, normalize L2 chỉ trên terms có trong vocabulary.
E2 indices bắt đầu từ len(terms); missing sparse text term có giá trị 0.

Mỗi cây duyệt <= threshold, tôn trọng missing_type/default_left trong JSON.
Cộng leaf values của 400 cây rồi sigmoid; leaf values đã chứa shrinkage và initial score.
Không nhân learning_rate thêm. Score chưa calibrated, không hiện thành % an toàn.
KD threshold=0,6204500086017339; hard threshold=0,6157178977907972.
Sai input/load/hash phải báo lỗi, không trả benign giả.

Python:
```powershell
python scripts/predict_lightgbm_student.py --examples
python scripts/predict_lightgbm_student.py --mode hard_only example.com
```

Không cần Teacher, API hoặc dataset ở Student inference.
Dart adapter và Android offline measurements chưa có; Hy kiểm chứng trước khi nghiệm thu.
Ưu tiên hoàn thiện Teacher UI/offline/device QA theo lựa chọn engine hiện tại.

## Cho Khiêm

Chạy tests/test_student_lightgbm.py. Kiểm model/features/reference/PSL hashes, feature order,
native–JSON score, invalid inputs, threshold và fixtures từng mode.
CV targets/manifest.json lưu Teacher theo fold; Teacher được load từ cache đã có, không fit lại.
Train Student từ exported targets không cần caches Teacher hoặc chạy lại benchmark tuần trước.
Giữ tests/metrics cũ. Python parity không phải Android parity.

## Cho Hưng — cách viết kết luận

Chưa có bằng chứng KD giúp rõ rệt trong 3-fold CV dù LightGBM mạnh hơn baseline LR.
Không quy lợi ích của hybrid features/boosting thành lợi ích riêng của KD.
Không giấu Validation AP tốt hơn Teacher; cũng không dùng nó chọn lại model/ngưỡng.
Class prevalence/source confounding, reused folds/Validation, in-sample fitting targets,
một cấu hình/T/alpha và chưa benchmark Android là các giới hạn còn lại.
Giữ Teacher v2 làm engine hiện tại; không nói Teacher đã production-ready hoặc Student vô ích nói chung.
