# Student LightGBM — bổ sung theo yêu cầu nhóm

Ngày chốt: 17/11/2026. Không mở thêm họ mô hình sau lượt này.
Kế hoạch máy đọc: configs/week7_lightgbm_student.json, commit local d6f3dc1 trước benchmark.
Notebook thống nhất: notebooks/07_student.ipynb.
Báo cáo tổng hợp: reports/week7_student_comparison.md.

## Cấu hình và câu hỏi

LightGBM 400 cây, 15 lá, learning_rate=0,05, min_child_samples=20,
reg_lambda=1; không subsample, không early stopping, không grid.
Input = canonical char TF-IDF 8.192 chiều (3–5 grams) + 20 E2 từ raw URL.
Giữ TF-IDF + LR C=1 làm baseline. Cả hai họ có hard-only và KD,
cùng seeds 42/43/44 và cùng fitting IDs trong từng fold.
Các seed trùng kết quả trong cấu hình deterministic; không coi SD=0 là robustness.

Hard-only học y thật. KD học q=0,5*y+0,5*Teacher raw score, temperature=1.
LightGBM dùng objective cross_entropy hỗ trợ q trong [0,1] trực tiếp:
loss = -q*log(p) - (1-q)*log(1-p). Không dùng binary objective với fractional labels.
LR baseline dùng weighted positive/negative copies như trước.
Raw Teacher score chưa calibrated. Chưa thử alpha/T khác, hard-Teacher labels hoặc logit matching.

## Teacher theo fold — đã được Phúc đồng ý

Teacher phát hành đã học toàn bộ Train nên không dùng weights đó để tạo targets cho
outer CV rồi gọi toàn bộ quy trình độc lập với held fold.
Dùng các stack_hist_outer0/1/2.joblib đã fit từ nghiên cứu trước:
- Mỗi Teacher chỉ fit trên hai folds còn lại, không có held labels/domain.
- Cùng SVM+HistGB→scaled LR và hyperparameters của Teacher v2.
- HistGB từng lưu early_stopping=auto nhưng do_early_stopping_=False, đủ 300 vòng;
  fitting partitions dưới 10.000 mẫu, tương đương budget cố định của bản release.
- Weights khác release, được ghi rõ trong cv_targets/manifest.json.
- Kiểm ID hashes, domain disjoint, fit ledger, architecture và đối chiếu toàn bộ held scores
  với OOF lịch sử (atol=1e-12). Hash model cache được ghi trước khi sử dụng.
- Không gọi fit Teacher, không thay file Teacher phát hành.

Targets là in-sample trong outer fitting set; chưa inner cross-fit targets.
Đây là outer-fold training separation, không phải nested KD hoàn chỉnh.
Reuse folds đã dùng trong nghiên cứu trước/adaptive comparisons không biến chúng thành final independent test.

Để người khác chạy Student không cần Teacher caches local, đã xuất:
artifacts/student_lightgbm/cv_targets/ gồm fitting targets, held references và lineage/hashes.
Chỉ cần caches khi tạo lại targets; script dừng rõ ràng nếu caches không có và targets chưa được bàn giao.
Không tái tạo Teacher trên máy người khác một cách ngầm định.

## Group CV và model cuối

Giữ đúng 13.078 Train IDs và 3 folds trong reports/tables/stacking/train_ids.csv.gz.
TF-IDF fit riêng từng fitting set; E2/reference không fit lại hoặc sửa công thức.
36 CV fits = 2 họ × 2 modes × 3 folds × 3 seeds.
CV metrics tại threshold 0,5 cố định. Mean AP lấy qua folds/seed; không tune trên held fold.

Chọn mode LightGBM bằng mean Train CV AP; hòa chọn hard-only, export seed 42 đã định trước.
Threshold model cuối lấy từ pooled Student Train OOF seed 42 theo FPR budget 1%.
Threshold đó là hậu xử lý cho export, không phải phép chấm outer-CV độc lập mới.

Sau khi chốt mode/threshold, fit hai mode LightGBM trên toàn Train, dùng targets cached từ
released Teacher v2 đã kiểm đúng bundle/data hashes. Chạy đủ 3 seeds; xuất seed 42.
Validation 1.585 mẫu, 24 phishing chỉ báo bổ sung sau freeze; không chọn lại theo Validation.
Không đọc/chấm Official Test/external, không thay official splits.

## Đóng gói, ngân sách và giới hạn

Gói có JSON/native LightGBM, vocabulary/IDF, E2 feature order, reference 45 brand,
PSL, threshold, SHA-256, nguồn targets và Python fixtures valid/invalid.
Model JSON có shrinkage và initial score trong leaf values; không nhân learning_rate lần hai.
Reference predictor không cần LightGBM/Teacher/API khi inference, nhưng Python package còn
dùng các thư viện và E2/parser đã pin. Mobile cần port và kiểm chứng riêng.

400 cây theo yêu cầu làm data package khoảng 1,19 MiB, vượt mục tiêu nghiên cứu cũ 1 MiB.
Không coi mục tiêu đó là Android budget đã được thống nhất, không giảm cấu hình để ép số liệu.
Chưa có Student Dart/Android parity, RAM, startup, latency hoặc APK measurements.

Teacher stacking v2 vẫn là engine tích hợp chính theo quyết định hiện tại.
LightGBM là candidate nghiên cứu, chưa promote; AP Validation cao hơn Teacher vẫn được báo cáo đầy đủ.

## Tái lập

```powershell
python -m pip install -r requirements-teacher.txt -e ".[teacher,test]"
python scripts/train_lightgbm_student.py
python scripts/summarize_student_comparison.py
python scripts/predict_lightgbm_student.py --examples
python -m pytest tests/test_student_lightgbm.py -q
```

Nguồn objective/parameters: https://lightgbm.readthedocs.io/en/stable/Parameters.html
