# Tuần 6 — Phúc: báo cáo ứng viên, chưa chốt Teacher

Trạng thái hiện tại là awaiting_team_decision. Mục tiêu của thay đổi này là báo kết quả thử thêm model cho nhóm, chưa xuất một Teacher mới để tích hợp.

## Đọc theo thứ tự

1. reports/week6_teacher.md: kết quả, giới hạn và điều nhóm cần quyết định.
2. notebooks/06_teacher_v1.ipynb: toàn bộ khai báo model và fit/predict.
3. reports/tables/week6/comparison.csv: 13 model, tách E2 và URL thô.
4. low_fpr_metrics.csv, errors.csv, teacher_selection.json và verification.json để kiểm tra sâu hơn.

## Phần nào đã làm?

- Giữ LR, LR balanced, RBF SVM, MLP, HistGB và RF.
- Thêm LightGBM, XGBoost, CatBoost, Extra Trees, Balanced RF.
- Thêm TF-IDF char n-gram + Linear SVM/LR làm đối chứng URL thô.
- Cùng 13.078 Train IDs, ba outer domain folds, inner Group CV; tuning AP trong fitting.
- Bảng AP/Recall/FPR/F1, tốc độ PC, kích thước; phân tích ngưỡng nhắm FPR 2% chỉ từ inner-OOF fitting.
- Phân tích 12 lỗi OOF của ứng viên E2 dẫn đầu, đủ FP/FN ở ba folds.
- Kiểm thử vocab/scaler/tuning/threshold không nhìn outer holdout; kiểm tra ID/folds và reload ứng viên.

CatBoost dẫn đầu E2: CV AP khoảng 0,7332. TF-IDF Linear SVM dẫn đầu URL thô: khoảng 0,9256. Cần đọc cả Validation và giới hạn source/format bias trong báo cáo; CV cao chưa chứng minh hiệu quả thực tế.

## Các bước notebook làm gì?

| Tag / bước | Công việc | Tại sao cần? |
| --- | --- | --- |
| setup | Import, paths, seed, CPU thread | Dùng môi trường/config rõ ràng |
| data | Nối X/URL/nhãn/domain theo ID, kiểm tra schema/hash | Tránh ghép nhầm hoặc dùng E2 v0 |
| models | Tạo trực tiếp 13 sklearn-style classifiers/Pipelines | Đọc ngay model và grid đang thử |
| helpers | Chia inner folds, chọn input, score, metric, threshold | Các phép lặp ngắn, không giấu một pipeline train khác |
| cv | GridSearchCV.fit hoặc clone(model).fit trong fitting, predict outer holdout | Tạo đúng một OOF prediction/ID/model |
| selection | Xếp hạng riêng ứng viên E2 và URL thô | Không tự chốt Teacher |
| final_fit | Tuning trên full Train, fit ứng viên, dự đoán Validation | Phục vụ báo cáo/demo, không chấm lại Train làm OOF |
| errors | Đọc 12 lỗi của E2 đứng đầu | Hiểu giới hạn 20 features |
| resources | Đo predict+score PC và dung lượng pipeline | Cân nhắc tài nguyên, chưa phải benchmark Android |
| save | Lưu báo cáo và metadata pending | Tránh bàn giao nhầm một model là Teacher cuối |
| demo | Thử hai ứng viên trên cùng năm URL offline | Xác nhận đường predict hoạt động, không xác minh nhãn |
| external | Ghi trạng thái chờ chốt; không chấm thêm | Không dùng external để chọn model |

Các hàm cần hiểu:
- inner_splits: chia hai group folds bên trong fitting, kiểm tra domain không giao nhau.
- model_input: E2 lấy đúng 20 cột số; text lấy duy nhất cột url.
- ranking_scores: probability hoặc SVM margin, phục vụ AP.
- calculate_metrics: AP/precision/recall/F1/FPR và TN/FP/FN/TP.
- threshold_at_train_fpr: lấy quantile benign từ inner-OOF fitting, dùng cho bảng phụ FPR thấp.

Lời gọi học nằm ngay trong cell cv/final_fit. train_teacher.py chỉ chạy notebook, không tạo một thuật toán huấn luyện khác.

## Những đầu ra nhóm có thể review ngay

Trong reports/tables/week6:
- comparison.csv: thứ hạng và tài nguyên; e2_contract_compatible cho biết có nhận 20 features hay không.
- cv_metrics.csv: kết quả từng outer fold; low_fpr_metrics.csv: kết quả phụ ở ngưỡng hiệu chỉnh trong fitting.
- oof_predictions.csv.gz: 170.014 dòng = 13 × 13.078; có model/ID/fold/nhãn/score.
- training_partitions.csv.gz: fitting/held_out/inner fold IDs để Hưng audit leakage.
- parameters.csv: tham số được chọn mỗi fold và full Train.
- validation.csv / validation_predictions.csv.gz: báo cáo riêng; không dùng chọn model.
- resources.csv: scope đo riêng cho numeric E2 và text.
- errors.csv: 12 lỗi E2, có observation/hypothesis/next_check.
- demo_predictions.csv: chỉ minh họa candidate_not_final_teacher.
- teacher_selection.json: tên file giữ từ đợt trước, nhưng selected_candidate=null, teacher_finalized=false.
- external_results.json: NOT_RUN_PENDING_TEACHER, ghi rõ các quan sát lịch sử đã thấy.
- verification.json: kiểm chứng và hash.

Ví dụ Hưng đọc OOF:
~~~python
import pandas as pd

oof = pd.read_csv("reports/tables/week6/oof_predictions.csv.gz")
catboost_oof = oof.loc[oof["model"].eq("catboost")]
text_svm_oof = oof.loc[oof["model"].eq("tfidf_linear_svm")]
~~~

## Chạy lại trên local

Cài thêm các thư viện của đợt thử model:
~~~powershell
.\.venv\Scripts\python.exe -m pip install -e ".[teacher,test]"
.\.venv\Scripts\python.exe scripts/train_teacher.py
~~~

Cần có handoff core/E1 X/domains/folds và E2 v1 trainval như notebook data kiểm tra. Chạy lại sẽ ghi lại bảng/metadata tuần 6 và candidate local; không ghi đè raw, folds hoặc đầu ra tuần 5. Không cần chạy lại chỉ để đọc các kết quả đã commit.

Phiên bản thật có trong teacher_selection.json. Đã giữ nguyên các phiên bản core đang dùng khi cài model libraries.

## Vì sao chưa gọi predict_teacher như trước?

configs/week6_teacher_lock.json hiện có teacher_finalized=false. predict_teacher.py sẽ dừng với thông báo chờ nhóm quyết định, và load_locked_teacher cũng chặn trước khi mở artifact. Đây là trạng thái có chủ đích.

models/week6_teacher_v1.joblib vẫn giữ nguyên MLP từ commit 19ceb7b để không ghi đè lịch sử thành một lựa chọn mới. Nó chưa được tái xác nhận sau đợt so sánh này. Không lấy file đó để tuyên bố Teacher mới đã sẵn sàng.

Để review local, notebook save hai candidate trong data/interim/week6_candidate_e2.joblib và week6_candidate_raw_url.joblib. Hai file bị Git bỏ qua, chỉ phục vụ reload/demo; không cần gửi riêng hoặc đưa vào PR như Teacher chính thức. Hưng/Khiêm/Hy review bảng và protocol trước; bundle tích hợp cuối chỉ bàn giao sau quyết định nhóm.

## Điều nhóm cần chốt tiếp

1. Giữ Teacher nhận E2 20 số hay cho phép học trực tiếp từ URL thô?
2. Cân nhắc CV, giới hạn nguồn/định dạng, Recall/FPR, kích thước và hướng inference web/mobile.
3. Nếu chọn E2, ứng viên dẫn đầu là CatBoost; nếu chọn text, dẫn đầu là TF-IDF Linear SVM. Thứ hạng chưa tự biến thành quyết định.
4. Sau quyết định: xuất một Teacher, chốt preprocessing/feature order hoặc vectorizer, metadata/hash/lock, thử inference và kiểm thử tích hợp với Khiêm/Hưng/Hy.
5. Đọc ít nhất 10 lỗi đúng model được chọn; phần hiện có là lỗi ứng viên E2, chưa thay thế phân tích text nếu nhóm chọn text.
6. Chỉ sau khi khóa lại Teacher mới chạy external host-only riêng. Chưa chấm Official Test, làm KD hoặc export Android.

Joblib không chạy trực tiếp trong Dart/Flutter. Các số latency hiện chỉ đo PC, không bao gồm UI/network và không phải số đo điện thoại. Việc chuyển đổi/runtime/parity phải được thử sau khi chọn model.

## Giới hạn kiểm chứng

Xem reports/week6_teacher.md và verification.json. Verifier freeze E2 cũ không được sửa trong phần này; không tuyên bố các guard toàn repo/exact float equality đã pass. Test code không chứng minh chất lượng bên ngoài dữ liệu.

## Phạm vi review PR benchmark

PR #24 bàn giao bảng so sánh 13 model, OOF và protocol; chưa bàn giao Teacher mới để tích hợp. Các thí nghiệm preprocessing/hybrid TF-IDF ghép E2 + LR của Hưng ở nhánh nghiên cứu riêng chưa nằm trong bảng này, cần PR riêng.

Cài môi trường sạch bằng pip install -e ".[teacher,test]". Extra test có pytest/nbformat/IPython; extra teacher có các model libraries và nbclient/ipykernel cho runner. Workflow .github/workflows/week6-benchmark.yml chạy Python 3.11, import các thư viện bắt buộc, chạy Teacher fixtures không cho skip, rồi full pytest. Không retrain dataset hoặc truy cập website URL.

CI checkout chỉ có file được Git quản lý. Những test cần handoff/cache trong data/interim hoặc model local có thể skip và phải đọc lý do; không suy ra CI đã kiểm chứng integration với đầy đủ dữ liệu. Phần local kiểm tra artifact thật được ghi riêng trong verification.json tại handoff_review.

Kết quả 396 passed/1 skipped là lịch sử ngày 11/11/2026, không thay thế kết quả kiểm chứng mới của PR. Không chạy lại notebook chỉ để đổi tài liệu hoặc tiêu đề PR.
