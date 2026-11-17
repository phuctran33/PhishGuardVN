# Student tuần 7: protocol phát triển và cách đọc code

Căn cứ: [kế hoạch Student mới nhất](week7_student_offline_plan.md) và phân công tuần 7.
Protocol KD tuần 6 không áp dụng cho thí nghiệm này.
Cấu hình máy đọc được: [configs/week7_student.json](../configs/week7_student.json).

## 1. Câu hỏi và phạm vi

Một mô hình ký tự nhỏ có giữ được chất lượng đủ hữu ích khi học thêm Teacher v2 không?
So sánh đúng hai bản cùng kiến trúc/biểu diễn/ngân sách:
- **hard_only:** học nhãn thật PhishVN.
- **kd_mixed:** học mục tiêu q = 0,5 × nhãn thật + 0,5 × score Teacher.

Teacher v2 được load qua loader chính thức, giữ nguyên weights, threshold, E2 và reference.
Score Teacher chưa calibrated; q là mục tiêu mềm cho hàm loss, không phải nhãn xác minh mới.
Không temperature tuning, không grid search, không train thêm Teacher.

## 2. Dữ liệu và ranh giới đánh giá

Đọc trực tiếp hai file **đã tracked**: data/splits/url_train.csv và url_val.csv.
Không phụ thuộc data/interim hoặc notebook của người khác.
Lọc Gold/Silver, URL hợp lệ và có registrable domain theo parser hiện có.
Snapshot hiện tại: Train 13.078 (2.074 phishing), Validation 1.585 (24 phishing).
Hai mẫu Train không hợp lệ/unresolved được ghi theo ID và lý do trong exclusions.csv;
đây là eligibility đã có, không phải loại mẫu dựa trên dự đoán.

Giữ nguyên official splits, không tạo splits mới. Kiểm tra ID, registrable domain và
chuỗi canonical giữa Train/Validation; gặp overlap thì dừng để review, không tự chuyển mẫu.
Các URL cùng registrable domain thuộc một split. Có 2 canonical duplicates trong Train,
không có canonical overlap Train–Validation; không khẳng định đã tìm hết near-duplicates
hoặc quan hệ giữa các domain khác nhau.

Teacher đã fit trên Train nên targets là **in-sample, không cross-fit**. Điều này phù hợp
với mục đích bắt chước Teacher cố định trên Train; không được gọi là nested/OOF KD
hay bằng chứng độc lập trên các folds Train. Không tái sử dụng các OOF lịch sử làm targets.
Teacher scores của Validation chỉ để đối chiếu agreement, không đi vào fit Student.

Theo kế hoạch mới, dùng Validation chọn candidate/ngưỡng. AP chính; hòa chính xác chọn hard_only.
Với mỗi candidate: chọn khoảng ngưỡng thấp nhất cho FPR Validation <= 1%, lấy midpoint
để tránh boundary chỉ cách score một ULP khi port JSON; báo thêm ngưỡng 0,5.
Ngưỡng Teacher giữ nguyên. Validation đã được nhóm xem ở tuần trước và nay được dùng chọn
Student, nên metrics tại đây là **development metrics**, không phải final test độc lập.
Không đọc/chấm Official Test hoặc external trong pipeline này. Đánh giá cuối chỉ thực hiện
sau khi nhóm chốt artifact/chính sách; không tự chạy ở giai đoạn bàn giao sơ bộ.

## 3. Mô hình đơn giản

URL -> canonical_url đã đóng băng -> character n-grams 3–5 -> TF-IDF tối đa 8.192 cột
-> Logistic Regression (C=1, liblinear, seed=42, max_iter=2000).
Vocabulary và IDF chỉ fit trên Train; cả hai bản dùng cùng vocabulary.
Không dùng source/tier/ID/nhãn làm input features. Không dùng class weighting để tránh
trộn hiệu ứng KD với hiệu ứng thay đổi trọng số lớp.

Học q mềm bằng hai bản sao của mỗi hàng X: bản nhãn 1 có trọng số q, bản nhãn 0
có trọng số 1-q. Tổng trọng số mỗi mẫu vẫn là 1.
Loss tương đương -q*log(p) - (1-q)*log(1-p); có regularization của Logistic Regression.
Đây là soft-score distillation đơn giản, không phải temperature-scaled KL của protocol cũ.

Ngân sách: một seed, một cấu hình, hai cách học. Mục tiêu nghiên cứu model <= 1 MiB
(JSON weights + vocabulary/IDF); đây chưa phải giới hạn thiết bị đã thống nhất với Hy.

## 4. Cách chạy và flow

Dùng CPython 3.11, môi trường đúng requirements-teacher.txt, package được cài editable:

```powershell
python -m pip install -r requirements-teacher.txt -e ".[test]"
python scripts/train_student.py
python scripts/predict_student.py --examples
python -m pytest tests/test_student.py tests/test_teacher_release.py -q
```

Đọc main() trong scripts/train_student.py theo thứ tự:
1. load_data(): lọc/audit Train–Validation, lưu IDs/groups và exclusions.
2. load_released_teacher() rồi teacher_scores(): sinh Train targets; lỗi thì dừng.
3. TfidfVectorizer.fit_transform(Train), transform(Validation).
4. fit_student(): gọi LogisticRegression.fit trực tiếp với hai bản sao có trọng số.
5. Chọn threshold trên Validation, tính metrics, xuất JSON và đối chiếu JSON–sklearn.
6. Chọn candidate nghiên cứu bằng AP, đo desktop latency và ghi manifest.

Notebook 07_student.ipynb trình bày lại các bước học theo cách trực tiếp, không xuất đè release.
src/phishguard_vn/student.py chỉ chứa chuẩn hóa, vài hàm đánh giá và predictor JSON.
scripts/predict_student.py là điểm vào dự đoán; không cần Teacher hoặc dataset khi suy luận
Student. Python reference vẫn dùng code canonical/parser hiện có và các thư viện của project.

## 5. Bàn giao và điều chưa làm

artifacts/student_week7/ chứa hai model JSON, Teacher targets nén không có URL,
manifest hash/version và các URL tổng hợp để thử inference.
reports/tables/student_week7/ chứa bảng benchmark, dự đoán Validation theo ID,
latency desktop, source × label và split/exclusion audit.
Không thêm targets hoặc dự đoán Test. Không đưa URL thật vào các file kết quả mới.

Hy cần xác nhận ngân sách Android và làm adapter. Quy tắc TF-IDF: character theo Unicode
code points (không phải UTF-16 code units), giữ path/query case, sublinear TF=1+ln(count),
nhân IDF đã lưu, L2 normalize trên các terms trong vocabulary, dot coef + intercept,
sigmoid rồi so score >= threshold. Không cộng terms ngoài vocabulary vào L2 norm.
Phải tái hiện validate/canonical/whitespace giống Python, không chỉ port phép nhân ma trận.

Khiêm có thể kiểm tra manifest, JSON parity, invalid inputs và hash ngay; Android parity
chờ adapter. Chưa có số đo thiết bị, RAM, battery/thermal hoặc APK. Chưa đổi app mặc định.
Không tuyên bố Student sẵn sàng release/production hoặc đã hoàn thành tuần 7.
