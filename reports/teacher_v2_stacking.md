# Teacher v2 candidate: kiểm chứng stacking trên Train

Trạng thái: **candidate nghiên cứu, chưa promoted**. Teacher v1 raw TF-IDF/SVM vẫn là mặc định.
Số liệu bên dưới do lượt chạy của Phúc sinh ra, không chép benchmark tham khảo trong PDF.

## Kết luận để nhóm quyết định

Đề xuất hai nhánh **SVM trên URL canonical + HistGB trên 20 E2 raw**, kết hợp bằng StandardScaler + Logistic Regression.
Mean outer AP 0.930667 so với raw SVM 0.925628.
Chênh lệch nhỏ; CI paired còn chứa 0, chưa chứng minh thắng chắc.
Lợi ích đáng chú ý là độ ổn định trong những phép stress định dạng đã thử. Không suy rộng thành bất biến với mọi URL.

ExtraTrees thứ ba chỉ tăng AP khoảng 0,000464; CI chứa 0, kích thước và độ trễ tăng mạnh.
LightGBM hai nhánh nhỉnh AP khoảng 0,000183, CI cũng chứa 0; HistGB giữ runtime sklearn và file nhỏ hơn.
Hybrid SVM là đối chứng gọn (AP 0,927713). Không tự thay Teacher v1 dựa vào các chênh lệch này.

## Dữ liệu, kế hoạch và các bước đã chạy

- Eligible Train: 13.078 IDs, 2.074 phishing, 11.004 benign, 8.835 registrable-domain groups.
- Giữ nguyên raw/nhãn/folds/E1/E2/reference; 20 E2 = 12 lexical + 8 brand, tính từ raw URL.
- Plan hữu hạn `configs/teacher_v2_plan.json` đăng ký ở commit `64d97e1`, trước kết quả mới.
- 11 pipeline / 53 cấu hình, 3 outer folds cũ, 2 inner Group CV, seed 42.
- Outer-fitting: inner CV chọn cấu hình theo AP. Base của stacking tạo 2-fold group OOF trong chính fitting rows để meta LR học.
- Sau chọn cấu hình, 2-fold OOF trên outer-fitting chọn ngưỡng cho mục tiêu FPR 1%/2%; không dùng nhãn outer.
- Vocabulary/IDF/scaler chỉ fit trên fitting rows; source/ID/label/domain group không là feature.
- 552 fits benchmark + 33 fits candidate = 585 thành công; không fit thất bại. Các base cố định được chia sẻ giữa meta grids chỉ khi fitting IDs giống hệt.
- 143.858 outer OOF rows; audit round-trip CSV kiểm ID/nhãn/folds, domain isolation ở inner/meta/threshold, hash tập fitting và metric/ngưỡng.
- Kết quả benchmark gốc được giữ nguyên. Bổ sung theo yêu cầu người dùng ở `configs/teacher_v2_addendum.json`, không rerun toàn grid.

Lệnh đã chạy (không phải yêu cầu chạy lại khi pull):
```powershell
python scripts/run_stacking.py
python scripts/summarize_stacking.py
python scripts/check_stacking_supplements.py
python scripts/package_stacking_candidate.py
python scripts/package_stacking_candidate.py --resume-frozen
python scripts/summarize_stacking.py --audit-only
```

Lần package đầu dừng do URL minh họa dùng TLD .example bị parser từ chối; bundle/lock đã lưu được giữ nguyên.
Sau sửa ví dụ, tiếp tục với --resume-frozen: **không refit và không ghi đè bundle/lock**.
Single/batch có sai khác số thực tối đa 1,67e-16; dùng atol=1e-12 và bắt nhãn khớp tuyệt đối.

Môi trường benchmark: Python 3.11, sklearn 1.9.1, numpy 2.4.6, pandas 3.1.0, LightGBM 4.7.0.
Đầy đủ versions/source/data hashes ở `tables/stacking/execution_manifest.json`.
Metadata giữ đúng revision chạy, không thay hash lịch sử để giả code mới sinh ra số cũ.

## Kết quả outer Group CV

AP/Recall/FPR/F1 là trung bình 3 folds. Native: SVM dùng estimator.predict ở margin 0;
HistGB/meta LR dùng native predict ở probability 0,5. Cột ngưỡng 1% là **recall / FPR outer thực đạt**, không bảo đảm đúng 1%.
Ngưỡng 2% và confusion matrices ở từng outer JSON.

| Pipeline | AP | Native recall | Native FPR | Native F1 | Policy 1%: recall / FPR | CV file MiB | p95 batch16 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| stack_hist_extra | 0.9311 | 81.34% | 1.64% | 0.8559 | 75.46% / 1.02% | 30.89 | 69.57 |
| stack_lgbm | 0.9309 | 81.58% | 1.74% | 0.8552 | 75.41% / 1.04% | 2.10 | 9.41 |
| stack_hist | 0.9307 | 81.82% | 1.74% | 0.8566 | 75.55% / 1.07% | 1.62 | 11.31 |
| stack_hist_lgbm | 0.9306 | 81.49% | 1.71% | 0.8553 | 75.51% / 1.07% | 2.63 | 14.24 |
| stack_extra | 0.9304 | 81.10% | 1.72% | 0.8527 | 74.88% / 1.04% | 30.36 | 79.06 |
| hybrid_svm | 0.9277 | 78.98% | 1.36% | 0.8483 | 75.36% / 0.96% | 1.09 | 7.27 |
| stack_hybrid | 0.9272 | 81.29% | 2.04% | 0.8464 | 73.63% / 1.02% | 2.18 | 10.70 |
| raw_svm | 0.9256 | 77.77% | 1.14% | 0.8463 | 75.89% / 0.87% | 1.08 | 2.48 |
| canonical_wide_svm | 0.9229 | 78.16% | 1.47% | 0.8405 | 75.07% / 1.05% | 1.09 | 3.03 |
| canonical_svm | 0.9193 | 76.91% | 1.25% | 0.8379 | 74.16% / 0.98% | 1.05 | 2.84 |
| histgb | 0.7234 | 50.15% | 1.97% | 0.6242 | 42.38% / 0.79% | 0.53 | 8.06 |

Chi phí: mean 3 fold-models, cùng 16 URL, CPU 2 threads, warmup 3/repeats 15, chỉ đo sau khi training dừng.
Bao gồm raw URL → E2/reference/preprocessing cần thiết → score; bỏ startup/model-load/network.
Không phải latency Android, không lấy file size làm peak RAM.
Full candidate riêng: 2.130.586 bytes (~2,03 MiB), p50 11,51 / p95 16,49 ms cho batch16, có cả trả nhãn.

## Bootstrap paired

2.000 draws seed42, resample domain clusters trong từng outer fold, cùng mẫu bootstrap giữa các model;
metric là mean-fold AP. CI 95% conditional trên fitted models/folds, không có refit uncertainty
hay multiple-comparison correction. Các folds đã được quan sát nhiều vòng, **không phải final test độc lập**.

| So sánh | Delta AP | CI 95% |
|---|---:|---|
| hybrid_svm − raw_svm | 0.002084 | [-0.004938, 0.009081] |
| stack_hist − raw_svm | 0.005039 | [-0.000570, 0.011136] |
| stack_lgbm − raw_svm | 0.005222 | [-0.000164, 0.011252] |
| stack_lgbm − stack_hist | 0.000183 | [-0.000500, 0.000933] |
| stack_hist_extra − stack_hist | 0.000464 | [-0.000339, 0.001413] |

## Stress định dạng: dữ liệu tổng hợp, không phải nhãn mới

Tái sử dụng outer models đã fit. Đổi scheme/case giữ path/query, không truy cập website.
Bảng dưới dùng native predict và nhãn dataset để chẩn đoán, không khẳng định HTTP/HTTPS là cùng tài nguyên.

| Pipeline | Phép biến đổi | Recall | FPR | Số nhãn đổi | Max score delta |
|---|---|---:|---:|---:|---:|
| raw_svm | add_https | 25.41% | 0.00% | 1211 | 2.895219 |
| raw_svm | remove_scheme | 77.77% | 1.50% | 40 | 1.786729 |
| raw_svm | uppercase_hostname | 3.23% | 0.06% | 1676 | 2.871982 |
| stack_hist | add_https | 81.82% | 1.74% | 0 | 0.000000 |
| stack_hist | remove_scheme | 81.82% | 1.74% | 0 | 0.000000 |
| stack_hist | uppercase_hostname | 81.82% | 1.74% | 0 | 0.138192 |

Raw SVM ban đầu recall 77,77%; thêm https còn 25,41%, đổi case hostname còn 3,23%.
Stacking giữ nhãn ở ba phép thử này. **Điểm số vẫn có thể đổi**:
22 hàng có E2 thay đổi khi đổi case (entropy trên raw); max score delta của stacking khoảng 0,138192.
Text canonical không đổi trong toàn bộ ba phép thử, nhưng toàn pipeline chưa được chứng minh bất biến.

Bổ sung kiểm tra hostname-only trên toàn bộ 13.078 URL: hostname text thực sự đổi ở 13.078 hàng;
path/query/userinfo/fragment/port và registrable domain đều giữ nguyên.
Tái tính bằng outer models: stacking có 0 flips ở cả native và ngưỡng fitting-OOF FPR 1%;
raw có 1.676 native flips / 1.614 flips ở policy 1%.
Bằng chứng ở `tables/stacking/hostname_case_recheck.csv` và `supplement.json`.

## Source bias: giới hạn chưa giải quyết

Trong Train, 0 phishing có scheme, còn 1.659 benign có scheme. Bảng **eligible Train source × label**:

| Source | Benign | Phishing |
|---|---:|---:|
| tinnhiem_org | 1659 | 0 |
| tinnhiem_web | 3362 | 0 |
| tinnhiemmang | 0 | 2074 |
| tranco | 4170 | 0 |
| tranco_vn | 1813 | 0 |

Nguồn và nhãn phân tách hoàn toàn trong snapshot này. Bỏ cột source khỏi input và chia domain là biện pháp chống
một số leakage, **không chứng minh đã loại source bias**. Mô hình vẫn có thể học proxy từ định dạng,
hostname hoặc đặc điểm thu thập dữ liệu. Chuẩn hóa scheme/case chỉ xử lý một phần dấu hiệu.
Chưa có thử nghiệm source-disjoint có cả hai lớp hoặc final test độc lập; không tuyên bố tổng quát tốt ngoài dataset.
Không sửa nhãn hay dataset để làm đẹp kết quả.

## HistGB: tách benchmark lịch sử và bổ sung candidate

Benchmark ban đầu dùng early_stopping=auto. 42 fit HistGB có nhiều nhất 8.719 fitting rows;
các model đã lưu đều có do_early_stopping_=False và n_iter_=300.
Giữ nguyên model/metric đó, không chạy lại grid.

Mọi fit candidate mới (full-Train inner/meta/threshold/refit) đặt **early_stopping=False** rõ ràng.
Full Train 13.078 hàng chạy đủ 300 vòng, không bật random internal-validation.
Chưa có full-Train candidate auto trước bổ sung này; không có model auto cần thay hoặc xóa.
Hàm `candidate_base()` trong package script thể hiện lựa chọn này trực tiếp.

## Candidate đã freeze và bàn giao

- Hai nhánh cố định: canonical char2–5/cap100k SVM C=1; HistGB 300 vòng, lr=0,05, leaves=15, early_stopping=False.
- Full-Train Group CV chọn meta LR C=0.1, scale=true.
- Ngưỡng 0.6945740700635259 từ full-Train 2-fold Group OOF, mục tiêu empirical FPR <=1%.
  Nhãn: score >= threshold; score meta LR **chưa calibrated, không phải phần trăm an toàn**.
- Canonical v1: host IDNA/lower, bỏ scheme/default port, giữ case/percent escapes path/query;
  **bỏ userinfo và fragment**, có mất thông tin. Input lỗi báo lỗi; không fallback benign.
- Bundle chứa reference snapshot; load không cần dataset/report/research cache hoặc file reference ngoài bundle.
- Artifact `models/teacher_v2_candidate.joblib`; lock `configs/teacher_v2_candidate_lock.json`.
- SHA256: `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`.
- Parity 13.078 inputs: score max error 0, labels bằng nhau; single/batch và portable CLI 5 URL đã chạy.
- 12 case FP/FN, hai mỗi loại ở ba folds, đúng policy outer-fitting OOF FPR 1%;
  có hai base scores, threshold, đặc trưng quan sát, hypothesis và next_check trong `candidate/error_cases.csv`.

## Validation/external sau freeze, chỉ bổ sung

Các scope này đã từng được quan sát; không dùng chọn candidate/params/ngưỡng, không retune sau xem kết quả.
V1 dùng native margin0, candidate dùng policy Train OOF FPR1%; không gọi là so sánh cùng FPR thực đạt.

| Scope | AP | Recall | FPR | TP/FN/FP/TN |
|---|---:|---:|---:|---|
| validation | 0.5549 | 62.50% | 0.90% | 15/9/14/1547 |
| external | 0.9813 | 40.22% | 14.29% | 37/55/1/6 |

External: 99 historical-hostname records =92 phishing/7 benign; 68 pending không làm ground truth.
Subset 92 phishing nằm trong cohort99, không cộng thành hai tập độc lập. Có báo theo nguồn trong evaluation.json.
Vẫn bỏ sót **55/92 phishing**; FPR chỉ dựa trên 7 benign. AP cao trên cohort lệch lớp không chứng minh an toàn thực tế.
Không crawl URL, không đánh giá Official Test, chưa KD/export/Android.

## Kiểm thử và phạm vi bàn giao

Full local research suite: **500 passed, 1 historical skip**, hai warning L1 lịch sử.
Skip là empty regression parameter set ở test_brand_regressions.py, không thêm skip mới.
CI có job fixtures stacking riêng, yêu cầu >=53 tests và không skip; CI thực xem PR/head, không dùng số local thay CI.
Portable inference đã kiểm thật với bundle: chỉ runtime sources + lock + model, không dataset/report/reference CSV.
Teacher v1 lock/bundle/adapter/CLI được so byte với 35c7d8d và giữ nguyên.

Nhóm cần quyết định promotion sau review. Candidate chưa thay default v1.

Provenance note: metadata gi? hash script ?? th?c ch?y ? l?n ??ng g?i. B?n script m?i l?u revision training trong bundle khi fit m?i v? gi? revision g?c khi resume; kh?ng s?a metadata/hash l?ch s? hay refit bundle hi?n t?i.
