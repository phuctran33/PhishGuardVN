# Phúc — báo cáo mở rộng ứng viên Teacher v1 tuần 6

**Trạng thái: chưa chốt Teacher; chờ nhóm quyết định.** Thực hiện ngay trên nhánh phuc-week6-teacher-v1 theo review Hưng. So sánh 13 model: 11 model nhận E2 v1 và hai đối chứng nhận URL thô. Không thu thập thêm URL, sửa dữ liệu/nhãn/folds/reference hoặc chấm Official Test.

## 1. Kết quả cần báo nhóm

- Trong nhóm **20 features E2 v1**, catboost dẫn đầu mean Group CV AP 0.7332; MLP cũ đạt 0,7264. Đây là thứ hạng so sánh, chưa phải quyết định Teacher.
- **TF-IDF char n-gram + Linear SVM** dẫn đầu nhóm URL thô, AP 0.9256; TF-IDF + LR đạt 0,9222. Đầu vào và kích thước biểu diễn khác E2, nên cần quyết định contract trước khi bàn giao.
- TF-IDF Linear SVM có Validation AP khoảng 0,4011; CV cao không đủ chứng minh tổng quát tốt. Validation chỉ có 24 phishing và khác phân bố; không dùng kết quả này chọn lại/tune model.
- **Chưa có Teacher mới để tích hợp.** teacher_selection.json ghi selected_candidate=null; lock ghi teacher_finalized=false. Script predict_teacher.py thông báo chờ quyết định.
- MLP trước mở rộng vẫn giữ nguyên trong models/week6_teacher_v1.joblib để tham chiếu commit 19ceb7b, không coi đó là quyết định sau đợt so sánh này.

Dữ liệu kết quả: [comparison.csv](tables/week6/comparison.csv), [low_fpr_metrics.csv](tables/week6/low_fpr_metrics.csv), [teacher_selection.json](tables/week6/teacher_selection.json).
Code chạy thật: [notebook 06](../notebooks/06_teacher_v1.ipynb). Hướng dẫn: [week6_phuc_handoff.md](../docs/week6_phuc_handoff.md).

## 2. Protocol và giới hạn so sánh

Dùng đúng 13.078 eligible Train IDs, 3 outer domain folds của Hưng và seed 42. E2 có 12 lexical + 8 brand features, reference 45 brand verified; ID/label/source/tier/split không vào X. Hai unresolved tiếp tục nằm ngoài ma trận. Validation 1.585 URL được tách riêng.

Mỗi outer fold giữ ngoài để chấm. Tuning chỉ trong 2 inner StratifiedGroupKFold thuộc fitting; scaler và TF-IDF nằm trong Pipeline. Vocabulary/IDF không fit trên toàn Train trước CV. Balanced RF resample riêng trong mỗi fit, không resample trước chia folds. Không dùng Validation, outer holdout, Official Test hoặc external làm eval_set/early stopping. Model không hội tụ làm dừng.

AP là average_precision_score, không phải accuracy hoặc PR-AUC hình thang. Xếp mean outer AP giảm dần, hòa thì F1 cao hơn, FPR thấp hơn rồi tên. Nhãn chính theo predict: ranh giới 0,5 cho xác suất, 0 cho SVM margin. Score chưa hiệu chuẩn thành nguy cơ thực tế.

**Đây là mở rộng sau khi nhóm đã xem kết quả cũ**, gồm CV/Validation/external. Grid được ghi nhận trước lượt mở rộng, không điều chỉnh theo external. Các outer folds đã dùng để so sánh/chọn ứng viên nhiều lần; mean/std chỉ mô tả so sánh, không phải ước lượng độc lập sau model selection hoặc khoảng tin cậy. Official Test vẫn để nguyên.

## 3. Các model và cấu hình đã thử

Giữ 6 mốc: LR, LR balanced, RBF SVM, MLP, HistGB và RF.
Thêm 5 model E2: LightGBM, XGBoost, CatBoost, Extra Trees và Balanced Random Forest.
Thêm 2 đối chứng: TF-IDF char 3–5 + Linear SVM/LR.

Mỗi họ có tối đa 2 cấu hình, khai báo trực tiếp ở cell models:
- SVM RBF: C 0,5/2; MLP: 32 hoặc 32–16 neurons; HistGB: 7/15 lá.
- RF/Extra Trees/Balanced RF: 200 cây, min_samples_leaf=2, max_depth=12/None.
- RF/Extra Trees dùng class_weight=balanced. Balanced RF dùng sampling_strategy=all, replacement=True, bootstrap=False; hai cách xử lý mất cân bằng này khác nhau.
- LightGBM: 200 cây, learning_rate=0,05, num_leaves=7/15, deterministic CPU, 1 thread.
- XGBoost: 200 cây, learning_rate=0,05, max_depth=3/5, hist CPU, 1 thread.
- CatBoost: 200 iterations, learning_rate=0,05, depth=4/6, 1 thread, không eval_set/use_best_model.
- TF-IDF: analyzer=char, ngram_range=(3,5), min_df=2, max_features=50.000, sublinear_tf=True, giữ chữ hoa/thường; C 0,5/2 cho Linear SVM/LR. LR text dùng liblinear.

Tham số đã chọn ở từng fold và full Train nằm trong [parameters.csv](tables/week6/parameters.csv); grid và phiên bản thư viện ghi trong metadata. Chưa thử Char-CNN/FastText/FT-Transformer/URL Transformer, là các hướng Hưng ghi tùy thời gian. Đợt này ưu tiên kiểm tra mô hình tabular và thông tin chuỗi URL trước.

## 4. Nhóm E2 — giữ hợp đồng 20 features

| Model | CV AP | Recall | FPR | F1 | p50 ms / 128 | Pipeline KiB |
| --- | --- | --- | --- | --- | --- | --- |
| catboost | 0.7332 | 49.81% | 1.57% | 0.6292 | 1.228 | 225.05 |
| mlp | 0.7264 | 50.10% | 1.88% | 0.6259 | 1.229 | 35.84 |
| hist_gradient_boosting | 0.7230 | 50.68% | 2.00% | 0.6279 | 2.978 | 143.55 |
| lightgbm | 0.7222 | 49.66% | 1.84% | 0.6222 | 2.057 | 181.38 |
| balanced_random_forest | 0.7192 | 73.24% | 16.45% | 0.5630 | 20.728 | 21771.63 |
| xgboost | 0.7183 | 46.29% | 1.39% | 0.6014 | 1.820 | 222.93 |
| random_forest | 0.7176 | 73.09% | 17.07% | 0.5557 | 21.007 | 5275.26 |
| extra_trees | 0.7065 | 81.77% | 25.52% | 0.5164 | 18.841 | 3218.21 |
| svm_rbf | 0.6547 | 46.29% | 1.56% | 0.5990 | 34.205 | 531.14 |
| logistic_regression | 0.6432 | 36.84% | 2.28% | 0.4942 | 1.162 | 2.44 |
| logistic_regression_balanced | 0.6327 | 74.35% | 19.24% | 0.5390 | 1.138 | 2.45 |

Ứng viên E2 dẫn đầu là catboost; full Train chọn {"depth": 6}. Mean AP std của CatBoost khoảng 0,0037, MLP khoảng 0,0174, chỉ là mô tả 3 folds. CatBoost hơn MLP khoảng 0,0068 AP; chưa có kiểm chứng độc lập để gọi cải thiện chắc chắn. CatBoost có FPR thấp hơn tại ngưỡng mặc định nhưng Recall vẫn chỉ khoảng 49,81%, bỏ sót nhiều phishing.

RF/Extra Trees/Balanced RF có Recall cao hơn ở ranh giới mặc định nhưng FPR khoảng 16–26%; không xem Recall tăng một mình là cải thiện. Ứng viên CatBoost lớn hơn MLP; bảng tài nguyên giúp nhóm cân nhắc, chưa dùng tài nguyên làm tiêu chí chọn mới sau khi xem kết quả.

## 5. Đối chứng URL thô — chưa đổi contract Teacher

| Model | CV AP | Recall | FPR | F1 | p50 ms / 128 | Pipeline KiB |
| --- | --- | --- | --- | --- | --- | --- |
| tfidf_linear_svm | 0.9256 | 77.77% | 1.14% | 0.8463 | 4.889 | 1523.58 |
| tfidf_logistic_regression | 0.9222 | 70.83% | 0.77% | 0.8098 | 5.647 | 1523.72 |

TF-IDF học các cụm 3–5 ký tự từ chuỗi URL, giữ những thông tin mà 20 số count/length/brand có thể làm mất. AP cao hơn là bằng chứng đáng xem xét trong cùng Train/folds, không phải xác nhận nguồn/định dạng không còn gây nhiễu.

Kiểm tra cách ghi URL của đúng 13.078 Train IDs:

| Lớp Train | Không có scheme | Có scheme |
| --- | --- | --- |
| benign | 9345 | 1659 |
| phishing | 2074 | 0 |

Không phishing Train nào có scheme, trong khi 1.659 benign có. Phần lớn benign cũng không có scheme, nên bảng này không giải thích toàn bộ điểm TF-IDF; nó cho thấy biểu diễn thô có thể học dấu hiệu của cách thu thập/nguồn. Các nguồn hiện còn source–label confounding. Group theo domain không loại bỏ mọi source/format bias.

Validation AP của hai model text giảm mạnh; phải báo cả kết quả và giới hạn, không quảng bá AP 0,9256 thành hiệu quả ngoài thực tế. Nếu nhóm chọn hướng URL thô, cần chốt normalization/vocabulary/runtime và đọc lỗi riêng cho model text; không dùng phần giải thích 20 features để giải thích model TF-IDF.



![So sánh AP và lỗi OOF ứng viên E2](figures/week6/teacher_comparison.png)

## 6. Phân tích phụ: ngưỡng nhắm FPR 2% trong Train

Trong từng outer fitting, chọn cấu hình bằng inner CV rồi clone model đó để tạo inner-OOF scores. Lấy quantile benign, xử lý ties để FPR calibration không vượt 2%; áp dụng nguyên ngưỡng vào outer holdout.

| Model | Recall outer | FPR outer thực tế | F1 outer |
| --- | --- | --- | --- |
| balanced_random_forest | 50.00% | 1.96% | 0.6228 |
| catboost | 53.18% | 2.05% | 0.6481 |
| extra_trees | 45.56% | 1.67% | 0.5890 |
| hist_gradient_boosting | 50.39% | 1.95% | 0.6264 |
| lightgbm | 48.80% | 1.64% | 0.6190 |
| logistic_regression | 35.58% | 1.98% | 0.4870 |
| logistic_regression_balanced | 31.92% | 1.96% | 0.4476 |
| mlp | 47.59% | 1.55% | 0.6108 |
| random_forest | 50.92% | 1.96% | 0.6310 |
| svm_rbf | 46.58% | 1.60% | 0.6008 |
| tfidf_linear_svm | 81.97% | 1.83% | 0.8554 |
| tfidf_logistic_regression | 80.57% | 2.11% | 0.8404 |
| xgboost | 48.70% | 1.81% | 0.6142 |

Đây là mean outer metrics tại **ngưỡng được hiệu chỉnh trong fitting**, không phải mọi model có cùng FPR outer chính xác 2%. Ví dụ CatBoost FPR outer khoảng 2,05%, TF-IDF Linear SVM khoảng 1,83%. Không chọn ngưỡng trực tiếp trên OOF đã gộp, không dùng Validation/external. Phân tích phụ không đổi operating point mặc định hoặc tự chốt Teacher.

## 7. Validation bổ sung

| Model | AP | Recall | FPR | F1 |
| --- | --- | --- | --- | --- |
| logistic_regression | 0.3489 | 54.17% | 2.05% | 0.3768 |
| logistic_regression_balanced | 0.3102 | 95.83% | 25.56% | 0.1031 |
| svm_rbf | 0.2448 | 50.00% | 1.41% | 0.4138 |
| mlp | 0.3931 | 50.00% | 2.31% | 0.3333 |
| hist_gradient_boosting | 0.4473 | 58.33% | 1.47% | 0.4590 |
| random_forest | 0.3854 | 95.83% | 27.87% | 0.0954 |
| extra_trees | 0.2775 | 100.00% | 42.54% | 0.0674 |
| balanced_random_forest | 0.3797 | 95.83% | 22.29% | 0.1165 |
| lightgbm | 0.4556 | 41.67% | 1.09% | 0.3922 |
| xgboost | 0.4780 | 37.50% | 1.09% | 0.3600 |
| catboost | 0.4488 | 58.33% | 1.47% | 0.4590 |
| tfidf_linear_svm | 0.4011 | 54.17% | 1.99% | 0.3824 |
| tfidf_logistic_regression | 0.3540 | 50.00% | 1.73% | 0.3810 |

Validation chỉ có 24 positive/1.585, so với 2.074/13.078 trong Train; domain/source/prevalence khác nhau hạn chế so sánh AP. XGBoost Validation AP cao nhất trong lượt này cũng không làm thay đổi ranking Train CV. Không thêm grid để chạy theo kết quả Validation.

## 8. Đọc 12 lỗi của ứng viên E2 dẫn đầu

[errors.csv](tables/week6/errors.csv) có 12 ID khác nhau, 2 FP và 2 FN ở mỗi fold, chọn theo thứ tự ID cố định. Mỗi dòng có observation/hypothesis/next_check. Đây là lỗi của catboost ở OOF, chưa phải lỗi của Teacher đã chốt; mẫu không đại diện ngẫu nhiên toàn bộ lỗi.

| URL đã vô hiệu hóa link | Fold | Lỗi | Score | Fitting trái nhãn cùng vector E2 |
| --- | --- | --- | --- | --- |
| kokatrade[.]com | 0 | FN | 0.1339 | 67 |
| mrhmfund[.]com | 0 | FN | 0.1546 | 25 |
| vn-inc[.]info | 2 | FN | 0.4801 | 0 |
| b1dv[.]xyz | 1 | FN | 0.2847 | 0 |
| pos365[.]vn | 0 | FP | 0.5024 | 5 |
| masothue[.]biz | 1 | FN | 0.1752 | 18 |
| pinuian[.]top | 2 | FN | 0.1588 | 39 |
| 11478[.]com | 2 | FP | 0.5741 | 0 |
| vnpayment[.]vn | 1 | FP | 0.6393 | 0 |
| 24hstore[.]vn | 0 | FP | 0.5469 | 3 |
| https://www[.]paypal[.]com | 1 | FP | 0.8397 | 4 |
| h-chan[.]me | 2 | FP | 0.7846 | 28 |

- kokatrade/mrhmfund/masothue/pinuian không có tín hiệu brand và cùng vector E2 với nhiều fitting URLs trái nhãn. Khác chuỗi nhưng cùng count/length/entropy/flags có thể không tách được bằng mọi model trên cùng 20 số.
- b1dv bật homoglyph_brand_hit nhưng vẫn FN: một flag không buộc model dự đoán phishing.
- vnpayment có mismatch/token; cần đối chiếu matcher/reference, chưa kết luận một feature là nguyên nhân FP hoặc tự thêm whitelist theo nhãn holdout.
- paypal không bật 8 brand flags trong reference hiện tại; không nói model đã nhận đúng official domain.
- pos365/24hstore/11478/h-chan cho thấy chữ số, gạch ngang, độ dài có thể xuất hiện ở benign. Không dùng 12 lỗi này làm lý do tune rule khớp riêng mẫu.
- “Trái nhãn cùng vector” không chứng minh URL trùng, nhãn sai hay nguyên nhân nhân quả; dữ kiện chỉ lấy trong fitting fold tương ứng.

## 9. Tài nguyên, web/mobile và trạng thái bàn giao

Tốc độ trong bảng là PC predict+score, 1 thread, batch 128, 5 warm-up + 30 repeats. E2 dùng X đã trích; TF-IDF gồm vector hóa từ URL. Hai phạm vi đo khác nhau đã ghi từng dòng resources.csv. Không phải end-to-end URL→API/UI, peak RAM hoặc benchmark Android.

Pipeline CatBoost khoảng 225 KiB; TF-IDF Linear SVM khoảng 1,49 MiB, gồm từ điển/IDF và classifier. Joblib phụ thuộc Python/thư viện, không chạy trực tiếp bằng Flutter/Dart. Web/mobile có thể dùng API Python sau khi chọn model và kiểm thử tích hợp. CatBoost có hướng xuất ONNX-ML cho numeric features theo [tài liệu chính thức](https://catboost.ai/docs/en/concepts/apply-onnx-ml), nhưng chưa export, chạy runtime hay đối chiếu parity trên Android. Với TF-IDF cần bảo toàn vocabulary/IDF và cách tạo char n-gram, chưa có triển khai mobile được kiểm chứng.

- OOF 170.014 dòng = 13 model × 13.078 IDs; cùng folds/partitions cho Hưng kiểm tra.
- comparison/cv_metrics/low_fpr_metrics/resources/parameters/validation/errors và metadata đã ở repo.
- Hai candidate local nằm trong data/interim, bị Git bỏ qua; không bàn giao như Teacher chính thức.
- models/week6_teacher_v1.joblib giữ MLP lịch sử từ commit 19ceb7b. Lock mới chưa chốt nên không được dùng nhầm.
- Demo 5 URL cho mỗi nhóm ghi rõ candidate_not_final_teacher; không truy cập website.
- Sau khi nhóm quyết định mới xuất Teacher, cập nhật feature contract/lock/hash, thử inference, phân tích lỗi đúng model được chọn và bàn giao Hưng/Khiêm/Hy.

## 10. External chưa chạy thêm trong lượt báo cáo này

external_results.json hiện ghi NOT_RUN_PENDING_TEACHER. Chưa dùng external để chọn giữa E2 và TF-IDF, chưa đánh giá external cho model text. Các CSV dự đoán của lần chốt trước được gỡ khỏi đầu ra hiện tại để tránh nhầm Teacher mới; kết quả MLP cũ vẫn tra được ở commit 19ceb7b.

Đã từng quan sát MLP 62/92 TP và CatBoost 59/92 TP trong phép thử hostname lịch sử; metadata ghi trung thực việc này, không coi external là tập chưa từng xem. Không dùng chênh lệch này quay lại chọn model. Cả hai phép thử có đúng 7 benign, FP=1; không phải bằng chứng generalization ngoài thực tế.

Nguồn vẫn là 167 candidates có sẵn từ Khiêm; ledger của Hưng có 99 đủ điều kiện historical-hostname (92 phishing/7 benign), 68 pending không tính metric. Hai CSV nguồn vẫn giữ pending. Không thu thập, đổi nhãn hoặc tự xem pending là ground truth. Sau khi nhóm chốt mới chạy external host-only riêng và báo theo nguồn.

## 11. Kiểm chứng

- Notebook 12/12 code cells không lỗi; code hash khớp metadata và bản kế hoạch ghi trước lượt chạy.
- 396 passed, 1 skipped in 29.56s; skip cũ do bộ tham số rỗng ở test_brand_regressions.py.
- Kiểm thử có scaler/search/vocabulary chỉ nhìn fitting, domain inner tách biệt, đổi đáp án outer không đổi dự đoán của fold đó, Validation không đổi ranking, threshold chỉ fit trên inner-OOF, trạng thái chưa chốt chặn inference Teacher.
- Recompute metrics chính và ngưỡng phụ từ OOF: sai khác tối đa 0.0.
- Sáu model cũ giữ nguyên OOF scores/predictions. 24 raw/input/artifact tuần trước giữ nguyên hash.
- Ứng viên E2 reload/direct URL khớp 6 Validation cases; portable candidate inference không dataset chạy 5 URL. Đây là kiểm tra candidate, không phải bàn giao Teacher.
- Bản audit chi tiết ở verification.json. Runtime revision/dirty ghi đúng trạng thái thực tế, không sửa thành commit sạch giả.
- Không sửa scripts/05_verify_e2_artifacts.py. Hai guard freeze toàn repo và exact equality float là giới hạn cũ đã ghi; không tuyên bố verifier cũ PASS.
