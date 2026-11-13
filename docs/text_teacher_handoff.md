# Teacher text v1 — bàn giao cho Hưng, Khiêm, Hy

Teacher đã được chọn theo yêu cầu nhóm: **tfidf_linear_svm**, raw URL, char 3–5, LinearSVC C=0.5. Mean outer Group CV AP 0,9256 là điểm quy trình so sánh trên folds đã quan sát nhiều lần, không phải đánh giá độc lập riêng cấu hình full Train.

## Bundle và cài đặt

Artifact hiện tại: models/teacher_tfidf_svm_v1.joblib (đưa vào Git để pull là có). Metadata/hash/versions: reports/tables/teacher_release/metadata.json. Lock chính thức: configs/week6_teacher_lock.json. models/week6_teacher_v1.joblib là MLP lịch sử, giữ nguyên và không dùng cho Teacher mới.

Cài Python 3.11 và pip install -e ".[inference,test]", bảo đảm scikit-learn==1.9.1 theo metadata. Inference chỉ cần sklearn/numpy/scipy/joblib và adapter teacher.py; không cần Torch, dataset, research folder, E2 hay brand reference.

~~~powershell
python scripts/predict_teacher.py example.com
python scripts/predict_teacher.py example.com "https://example.com/Case?Q=A"
python scripts/predict_teacher.py --examples
~~~

~~~python
from phishguard_vn.teacher import load_teacher

teacher = load_teacher(".")  # load một lần từ root repo
one = teacher.predict_one("example.com")
batch = teacher.predict_batch(["example.com", "https://example.com:8443/Path?Q=A"])
~~~

Adapter trả label/class_id, signed margin, model_version và preprocessing_version. benign=0, phishing=1. Margin dương nghiêng về phishing; **margin không phải xác suất hoặc phần trăm nguy cơ**. Nhãn luôn dùng estimator.predict, kể cả biên margin 0.

Contract input là chuỗi raw không rỗng, có thể thiếu scheme; chấp nhận Unicode/IDNA/port/path/query. Không strip/lower/normalize/truncate hoặc tự thêm scheme. Blank/NUL/sai kiểu bị từ chối, input validation không thay nội dung hợp lệ. Bundle thiếu/sai hash hoặc sklearn không tương thích trả lỗi rõ, không tự fit hoặc trả benign giả.

## Đóng gói và bằng chứng

scripts/package_text_teacher.py tái sử dụng candidate full Train có hash hợp lệ; không train lại benchmark/neural. Nó tách vectorizer và LinearSVC đã fit sang Pipeline sklearn thuần; vocabulary, IDF và classifier giữ nguyên. Candidate/bundle khớp score và nhãn trên 13.078 eligible Train + 5 ví dụ. Single/batch và lưu/load khớp. Fingerprints vocabulary/IDF/coefficients trong metadata.

Lock chỉ finalized sau parity; artifact/hash/version được ghi trước Validation/external. Đã thử CLI trong thư mục chỉ chứa adapter, bundle, lock, metadata — không dataset, research modules hoặc brand resources.

## Kết quả model đã khóa

Validation: 1.585 ID, 24 phishing / 1.561 benign. AP 0,401074; Precision 0,295455; Recall 0,541667; F1 0,382353; FPR 0,019859; TN=1530, FP=31, FN=11, TP=13. Validation đã được quan sát trước; không chọn lại cấu hình/threshold theo kết quả.

External: chỉ ledger đủ điều kiện hostname lịch sử, giữ nguyên review/eligibility. 92 phishing trong cohort hai lớp 99 (7 benign); đây là cohort overlap, **không phải hai tập độc lập**. TP=29, FN=63, FP=1, TN=6: recall=31,52%, FPR=14,29% (mẫu số chỉ 7). 68 pending không làm ground truth. Input hostname do audit cung cấp, không tự thêm scheme/path hoặc truy cập website. Có báo theo nguồn trong evaluation.json. Source/label/format bias và phạm vi historical host-only hạn chế kết luận; kết quả thấp vẫn giữ nguyên.

Official Test **chưa đánh giá**. Không nhận Teacher đã đạt hiệu quả production vì CV AP cao.

Bảng authoritative: reports/tables/teacher_release/validation_predictions.csv, external_predictions.csv, evaluation.json. Benchmark/nghiên cứu lịch sử giữ riêng, không ghi đè.

## Phân tích lỗi đúng TF-IDF SVM

oof_error_cases.csv có 12 case: 2 FP + 2 FN mỗi fold, chọn theo thứ tự ID cố định. Có ID, fold, y/prediction, margin, URL defang, observation/hypothesis/next_check. Không thay bằng lỗi CatBoost và không dùng full-Train coefficients giải thích OOF như thể cùng model. Không truy cập URL, sửa nhãn hoặc tune rule theo case.

## Phạm vi bàn giao

Hưng: dùng bundle và prediction/metrics đúng phiên bản/hash; external text adapter giữ nguyên audit rules. Khiêm: Python API/CLI single/batch và lỗi để test integration. Hy: contract raw URL và margin cho bước nghiên cứu export/runtime/parity sau.

Bundle Python **chưa chạy trực tiếp trong Dart**. Android offline, export/quantization, KD/Student chưa thực hiện. Chưa thay API/Web/Android của thành viên khác.

Lỗi cache pretrained nghiên cứu: prepare_url_research.py hiện kiểm tra hash cache nhưng chưa kiểm tra identity checkpoint/revision trước khi reuse cache nếu đổi plan. Không sửa trong đợt text Teacher này; cần bản vá riêng và test cache identity trước nghiên cứu pretrained tiếp. Teacher sklearn hiện tại không dùng checkpoint đó. Không sửa hash/lịch sử nghiên cứu để giả code mới tạo kết quả cũ.


## Ki?m ch?ng local

52 adapter/external tests passed; full research environment 438 passed, 1 skipped c? (brand regression r?ng), 2 warnings API L1 l?ch s?. CLI/Python parity ch?nh x?c; portable CLI th? 5 URL kh?ng dataset/research/reference. GitHub CI xem checks c?a PR, kh?ng nh?m v?i s? local.
