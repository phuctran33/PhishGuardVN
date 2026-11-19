# PhishGuardVN · Student KD với URL bronze cho Android offline

## Thiết kế và dữ liệu

Tất cả AP trong báo cáo là trung bình AP của ba fold theo tên miền trên **13.078 URL Gold/Silver Train** thuộc **8.835 nhóm domain**. Có 2.074 phishing và 11.004 benign. Các fold phát triển từng được dùng trong các thí nghiệm Teacher và Student. Seed mới kiểm tra độ nhạy với huấn luyện trên các fold đó. Chúng không tạo một tập Test mới. Validation, Official Test và external nằm ngoài benchmark này.

Dữ liệu bổ sung lấy từ **23.829 URL bronze thuộc split Train**. Runner bỏ URL trùng trong bronze và URL trùng với Gold/Silver sau khi chuẩn hóa, rồi loại domain của fold đang đánh giá. Lượt kiểm này không tìm thấy bản trùng ở bước đầu. Theo thứ tự fold 0–2, số domain-trùng bị loại tương ứng với 248, 506 và 246 URL, để lại **23.581, 23.323, 23.583** URL. Các cấu hình 512, 2.048 và 8.192 đều lấy phần đầu của cùng một danh sách đã sắp theo hash ID. Nhãn bronze gốc không tham gia chọn mẫu, loss hoặc đánh giá. Một fold Teacher gán nhãn cho phần fitting Gold/Silver và bronze đủ điều kiện của chính fold đó. Cả ba Teacher lưu sẵn đều khớp SHA-256 và có sai khác điểm tối đa bằng 0 khi chấm lại hàng Gold/Silver giữ lại. Mỗi Teacher đánh dấu khoảng 68–70% bronze đủ điều kiện là dương tại ngưỡng 0,5. Đây là phân bố điểm Teacher trên bronze.

- **A** học BCE từ nhãn thật Gold/Silver.
- **B** học Gold/Silver với điểm đích `(1−α) × nhãn thật + α × điểm Teacher`. Mặc định `α = 0,9`.
- **C** thêm BCE trên bronze với nhãn nhị phân `Teacher score >= 0,5`.
- **D** thêm BCE trên cùng các hàng bronze với điểm Teacher liên tục. C và D giữ cùng mô hình, preprocessing, seed, các hàng bổ sung và trọng số.

Mỗi nhóm lấy mean riêng. Ví dụ trong screening, D cộng `0,25 × mean BCE(bronze)` vào `mean BCE(Gold/Silver)`. Mỗi hàng bronze có trọng số bằng `λ × số hàng core / số hàng bronze` nếu hàng core có trọng số 1. Có kiểm tra số học độc lập cho công thức BCE và gradient. Boosters dùng objective nhận điểm mềm hoặc cặp bản sao 0/1 có trọng số. CART và rừng dùng entropy và xác suất lá có trọng số. Rừng tắt bootstrap độc lập từng bản sao. Naive Bayes tích lũy khối lượng theo lớp với smoothing. Các mô hình tối ưu loss theo khối lượng chuẩn hóa giữ tỷ lệ giữa hai nhóm. L2 của các mô hình đó tính trên loss đã chuẩn hóa. MLP, CNN và Factorization Machine dùng số bước cập nhật cố định trong mỗi phép so sánh.

**Biểu diễn đầu vào.** LightGBM, XGBoost, CatBoost, HistGB, RandomForest, ExtraTrees và CART dùng 20 đặc trưng E2 đóng băng. Logistic Regression, Naive Bayes, Factorization Machine, mô hình tuyến tính với đặc trưng RBF ngẫu nhiên và MLP dùng TF-IDF ký tự 3–5, tối đa 4.096 chiều. Vocabulary và IDF fit trên Gold/Silver fitting của từng fold. CNN đọc tối đa 128 byte UTF-8 từ URL chuẩn hóa, với padding riêng. Phần scoring offline chỉ cần dữ liệu mô hình và tài nguyên trích đặc trưng.

## Các giai đoạn đã chạy

| Giai đoạn chính | Seed | Phạm vi | Số fit |
|---|---|---|---:|
| Screening | 42 | 13 họ, hai cấu hình mỗi họ, A/B/C/D trên ba fold | 312 |
| Quét | 42 | 4 họ, 6 cấu hình D mỗi họ, trên ba fold | 72 |
| Xác nhận | 43, 44, 45 | 4 họ đã khóa, hai bản hard và ba bản KD mỗi họ | 180 |
| Kiểm tra đầu tiên trên ba seed cuối | 46, 47, 48 | CART đã khóa, hai bản hard và B/C/D | 45 |

Quét từng trục quanh `α=0,9, λ=0,25, n=2.048` với các mức khác `α=0,5 hoặc 1`, `λ=0,1 hoặc 0,5`, `n=512 hoặc 8.192`. Chọn bốn họ theo tăng AP so với bản A tốt nhất trong hai cấu hình đã thử. Ở lượt xác nhận, xếp theo số seed thắng, mức tăng của seed thấp nhất, mức tăng trung bình rồi AP tuyệt đối. Lưu cả A cùng cấu hình và A được chọn từ menu. Các bảng kiểm tra mở rộng đánh giá riêng tác động của việc nới menu tuning. Khoảng 95% dùng 1.000 lượt bootstrap ghép cặp theo domain, lấy mẫu trong từng fold và giữ cùng tập URL cho các mô hình và seed. Khoảng tin cậy có điều kiện trên tập domain, fold và các mô hình đã fit, chưa điều chỉnh việc thử nhiều cấu hình.

## Screening trên seed 42

Mỗi dòng ghi bốn chế độ ở cấu hình của biến thể KD có AP tốt nhất trong họ. Cột A tốt nhất lấy giá trị lớn hơn trong hai cấu hình A. Các cây đều chỉ thấy E2 nên AP giữa các họ phản ánh cả đầu vào lẫn thuật toán.

| Họ | A cùng cấu hình | A tốt nhất | B | C | D | KD tốt nhất trừ A tốt nhất |
|---|---:|---:|---:|---:|---:|---:|
| CART | 0,60529 | 0,60529 | 0,63089 | 0,66038 | 0,64703 | +0,05509 |
| MLP TF-IDF | 0,89004 | 0,89279 | 0,89576 | 0,88994 | 0,90094 | +0,00815 |
| LightGBM | 0,72175 | 0,72175 | 0,72495 | 0,72214 | 0,72465 | +0,00320 |
| RBF random features | 0,59783 | 0,59783 | 0,60029 | 0,56210 | 0,56808 | +0,00246 |
| HistGB | 0,72076 | 0,72076 | 0,72280 | 0,71540 | 0,71871 | +0,00204 |
| CNN byte | 0,82396 | 0,82396 | 0,82574 | 0,79816 | 0,81256 | +0,00178 |
| XGBoost | 0,72215 | 0,72215 | 0,72391 | 0,71802 | 0,71791 | +0,00176 |
| ExtraTrees | 0,68543 | 0,68543 | 0,68529 | 0,68180 | 0,68708 | +0,00165 |
| Factorization Machine | 0,89567 | 0,89567 | 0,89672 | 0,88501 | 0,89469 | +0,00105 |
| Logistic Regression TF-IDF | 0,90331 | 0,90331 | **0,90403** | 0,89153 | 0,90283 | +0,00072 |
| CatBoost | 0,72901 | 0,72901 | 0,72702 | 0,72264 | 0,72329 | −0,00198 |
| RandomForest | 0,71627 | 0,71627 | 0,71408 | 0,70669 | 0,70869 | −0,00218 |
| Naive Bayes | 0,85135 | 0,85135 | 0,84771 | 0,84378 | 0,84555 | −0,00364 |

CNN lớn dùng embedding 8 chiều, 24 filter độ rộng 5, ReLU và global max pooling. Chạy cố định 384 bước Adam. CNN nhanh về số lượng tham số nhưng triển khai NumPy mô hình này có chi phí đáng kể cho từng URL. Bộ cấu hình này đạt 0,82574 AP ở B và 0,81256 ở D. Mốc development 0,8767 được người dùng nêu chưa có cấu hình và artifact để đối chiếu trực tiếp trong lần kiểm chứng này.

## Kiểm tra ứng viên chính

### CART và độ nhạy với tuning hard

Với cây đã khóa (tối đa 9 tầng, ngưỡng tổng trọng số tối thiểu ở lá 0,0005), các seed 46–48 cho A/B/C/D lần lượt **0,60844 / 0,63087 / 0,65927 / 0,66669**. D tăng **0,05826** so với A cùng cấu hình, khoảng 95% **[0,00535, 0,10586]**, thắng 3/3 seed và 9/9 fold–seed. Chênh lệch trung bình riêng từng fold là +0,00733, +0,14892 và +0,01852. Nhãn mềm bronze chỉ hơn nhãn cứng bronze **0,00742 AP**, khoảng **[−0,00136, 0,01603]**.

Khi mở rộng baseline hard lên 28 tổ hợp, hard tối ưu theo seed 42 là cây depth 16 với ngưỡng trọng số lá 0,002. Trên seed 46–48, bản này đạt **0,68397**, vượt cấu hình KD đã khóa **0,01728**. Khoảng 95% của KD trừ hard là **[−0,02747, −0,00601]** và KD thua cả 9 fold–seed. Kết quả này sửa cách diễn giải ban đầu của mức tăng +0,05826. Cấu hình hard quá giới hạn có thể làm mức tăng KD trông lớn hơn. [Đối chiếu baseline hard rộng](tables/student_bronze_kd/cart_hard_sensitivity_paired_ap.csv)

### MLP, LightGBM và RBF trên lượt xác nhận

MLP 64 nút với D dùng `α=0,9, λ=0,25` và **8.192 bronze mỗi fold** đạt **0,90220 AP** trên seed 43–45. Mức tăng **+0,00863** so với A tốt nhất của menu hai cấu hình có khoảng **[0,00512, 0,01231]**. So với A cùng 64 nút, mức tăng là **+0,01288**, khoảng **[0,00860, 0,01732]**. D hơn C **+0,00650**, khoảng **[0,00460, 0,00856]**. Cả ba phép so của D thắng đủ 9 fold–seed. [Bảng xác nhận ghép cặp](tables/student_bronze_kd/confirm_paired_ap.csv)

LightGBM D dùng 512 bronze tăng **+0,00350** so với hard, khoảng **[−0,00569, 0,01776]**. D cao hơn C **+0,00806**, đồng thời khoảng D trừ A vẫn chứa 0. RBF dùng riêng KD Gold/Silver tăng **+0,00294** so hard, khoảng **[0,00149, 0,00426]**, nhưng bản D giảm **0,03425 AP** và gói dữ liệu lớn hơn 4 MB. CatBoost, RandomForest và Naive Bayes đều có KD tốt nhất thấp hơn hard trong screening. Tín hiệu nhỏ từ HistGB, XGBoost, ExtraTrees, Factorization Machine, CNN và Logistic Regression ở seed 42 cần đọc như quan sát screening.

## Kết luận sau khi mở rộng tuning cho hai ứng viên

### CART với menu tuning như nhau

Lượt mở rộng dùng cùng **28 tổ hợp độ sâu và ngưỡng trọng số lá cho cả A, B, C và D**. Khóa cấu hình trên seed 42, rồi chạy seed 49–51. D tốt nhất đạt **0,69243**. A tốt nhất đạt **0,68343**. Chênh lệch **+0,00900**, khoảng **[−0,00138, +0,02078]**, thắng **3/3 seed và 2/3 fold**. Riêng so sánh D với C cùng cây cho **+0,02573**, khoảng **[0,01382, 0,03707]**, thắng 9/9 fold–seed. Điểm mềm có ích so với làm tròn điểm Teacher cho cây này. Ưu thế so với hard được tuning công bằng vẫn chưa chắc. [Bảng CART menu 28 cấu hình](tables/student_bronze_kd/cart_wide_final_paired.csv)

### MLP TF-IDF là Student hưởng lợi KD rõ nhất

Giữ D đã khóa từ lượt xác nhận, 64 nút ẩn, `α=0,9, λ=0,25`, 8.192 bronze, 384 bước Adam. Mở rộng A thành **9 tổ hợp** của 16/32/64 nút và learning rate 0,0015/0,003/0,006, giữ số bước và batch size. Chọn A trên seed 42 trước khi đánh giá trên **49, 50, 51**. A thắng menu là **64 nút, learning rate 0,0015**.

| So với MLP D cố định | AP đối chứng | AP D | Δ AP | Khoảng 95% | Thắng fold / seed |
|---|---:|---:|---:|---:|---:|
| A cùng 64 nút, cùng learning rate và số bước | 0,88844 | 0,90206 | **+0,01362** | [0,00943, 0,01790] | 3/3 · 3/3 |
| A được chọn từ 9 cấu hình | 0,89461 | 0,90206 | **+0,00745** | [0,00418, 0,01103] | 3/3 · 3/3 |
| B KD Gold/Silver | 0,89348 | 0,90206 | +0,00858 | [0,00549, 0,01182] | 3/3 · 3/3 |
| C, cùng 8.192 bronze nhưng nhãn Teacher cứng | 0,89552 | 0,90206 | **+0,00654** | [0,00455, 0,00874] | 3/3 · 3/3 |

Đây là mức tăng dựa trên ba fold phát triển đã dùng lại. Với hard tuning trong phạm vi số bước đã khóa, MLP giữ được một mức tăng vừa phải và ổn định hơn CART. Kết quả D so với C xác nhận có tín hiệu riêng từ độ mềm của điểm Teacher cho đúng tập bronze, ngoài việc chỉ có thêm URL. [Khóa MLP](tables/student_bronze_kd/mlp_final_lock.json) · [Các cặp kiểm thử MLP](tables/student_bronze_kd/mlp_final_paired_ap.csv)

**AP tuyệt đối cao nhất trong menu nghiên cứu là Logistic Regression TF-IDF B, 0,90403** ở screening. Bản hard của nó đạt 0,90331. Nếu mục tiêu là phân tích tác dụng của KD thì ưu tiên kết quả MLP. Nếu mục tiêu là thử một Student có chất lượng và chi phí tốt trên Android, ưu tiên Logistic Regression.

Tổng cộng **1.164 lượt fit có đánh giá** gồm 609 lượt chính, 93 đối chứng CART hard mở rộng, 381 lượt CART cùng menu rộng, và 81 lượt kiểm tra MLP. Con số này không cộng lại các lượt phát lại để xuất hoặc đo chi phí. [Biểu đồ khoảng tin cậy](figures/student_bronze_kd/paired_gain.png)

## Chi phí inference và khả năng đưa sang Android

Đo **250 URL giống nhau ở fold 0** từ chuỗi URL thô đến score trên Windows, một luồng, có warm-up. Chi phí bao gồm preprocessing và model, bỏ thời gian khởi tạo. Tất cả model đại diện được fit lại bằng cấu hình đã ghi và kiểm score với checkpoint cũ trước khi đo. Dữ liệu là model và vectorizer dạng joblib nén cùng dữ liệu PSL/reference nếu cần. Tệp ZIP di động của một số họ dùng định dạng riêng, do đó kích thước của nó được ghi riêng.

| Mô hình đã đo | Giai đoạn | AP | Dữ liệu, byte | p95 CPU Windows |
|---|---|---:|---:|---:|
| Logistic Regression TF-IDF B | Screening | **0,90403** | 138.704 | **0,502 ms** |
| Logistic Regression TF-IDF A | Screening | 0,90331 | 138.678 | 0,519 ms |
| MLP TF-IDF D, 8.192 bronze | Xác nhận | 0,90220 | 1.086.524 | 4,568 ms |
| CART D, cùng cây đã khóa | Kiểm tra seed 46–48 | 0,66669 | 99.317 | 1,197 ms |
| CNN byte B | Screening | 0,82574 | 87.076 | 4,862 ms |
| RBF random features B | Screening | 0,60029 | 4.020.459 | 0,560 ms |

Gói CART D chứa cây JSON và cả dữ liệu tiền xử lý, dung lượng **34.033 byte**. [Gói cây CART nghiên cứu](../artifacts/student_bronze_kd/final/cart_large_D_0.9_0.5_2048.portable.zip) · [Bảng đầy đủ 35 phép đo](tables/student_bronze_kd/offline_cpu_cost.csv)

Với ngưỡng tham khảo **gói dữ liệu ≤ 1 MiB và p95 CPU Windows ≤ 1 ms**, Logistic Regression TF-IDF là ứng viên Android ưu tiên do AP cao nhất trong các model đạt cả hai mức. Đây là ngưỡng dùng so sánh trên máy local. AP nhãn thật đã là 0,90331 nên chênh lệch 0,00072 ở screening chưa đủ để chọn chế độ KD cho bản phát hành. Máy local thiếu môi trường Android để đo p95, RAM, APK hoặc đối chiếu score trên thiết bị. [Bảng Android proxy](tables/student_bronze_kd/android_tradeoff.csv) · [Biểu đồ AP và chi phí](figures/student_bronze_kd/offline_tradeoff.png)

Gói Logistic Regression chế độ B (KD trên Gold/Silver) dạng dữ liệu ZIP có **83.491 byte**, gồm vectorizer, hệ số, PSL và manifest. Bộ suy luận chỉ đọc dữ liệu cho điểm khớp trên **4.359 URL holdout fold 0**, sai số tối đa **4,44 × 10⁻¹⁶**. p95 của bộ suy luận này là **0,098 ms** trên Windows. ZIP là prototype score-only của fold 0. Để thử bản A trên Android, cần fit và xuất đúng bản học nhãn thật rồi đối chiếu điểm trên thiết bị. [Gói Logistic Regression offline](../artifacts/student_bronze_kd/lr_portable/student_score.zip) · [Kiểm chứng ZIP](../artifacts/student_bronze_kd/lr_portable/verification.json)

Nén MLP D xuống int8 ở lớp đầu giảm gói mô hình và PSL từ **1.067.575 xuống 323.978 byte**, khoảng 70%. AP tính lại trên cả chín lượt fold–seed là **0,90207** với int8 và **0,90206** với float32. Bộ đọc tham chiếu giải lượng tử về float32 trước khi suy luận, p95 **0,303 ms** trên cùng 250 URL Windows. Đây là kiểm chứng về kích thước lưu trữ và score, với một cấu hình MLP đáng đem sang thử trên thiết bị nếu nhóm cần demo KD. [Bảng nén MLP](tables/student_bronze_kd/mlp_compression.csv) · [Dữ liệu MLP int8](../artifacts/student_bronze_kd/mlp_final/compact/mlp_int8.npz)

## Tái lập và xem raw predictions

Chạy từ thư mục gốc bằng Python 3.11 trong môi trường dự án. Trên checkout mới, nếu tạo lại cache Teacher hoặc refit Teacher, hãy lưu riêng thư mục kết quả đã tải về và bắt đầu các bước dưới đây với thư mục `reports/tables/student_bronze_kd` mới. Các khóa giai đoạn của lần chạy đã xuất gắn với hash cache của lần đó. Dùng các phiên bản dependency trong manifest. Lệnh tests dưới đây xác nhận phần Student và Teacher có sẵn, kết quả **85 passed** cùng 5 cảnh báo Pandas deprecation.

```powershell
.\.venv\Scripts\python.exe scripts/kd_bronze_trees.py
.\.venv\Scripts\python.exe scripts/kd_bronze_sparse.py
.\.venv\Scripts\python.exe scripts/kd_bronze_data.py
.\.venv\Scripts\python.exe scripts/kd_bronze_runner.py --stage screen
.\.venv\Scripts\python.exe scripts/kd_bronze_stages.py screen
.\.venv\Scripts\python.exe scripts/kd_bronze_runner.py --stage sweep
.\.venv\Scripts\python.exe scripts/kd_bronze_stages.py sweep
.\.venv\Scripts\python.exe scripts/kd_bronze_runner.py --stage confirm
.\.venv\Scripts\python.exe scripts/kd_bronze_stages.py confirm --bootstrap
.\.venv\Scripts\python.exe scripts/kd_bronze_runner.py --stage final
.\.venv\Scripts\python.exe scripts/kd_bronze_stages.py final --bootstrap
.\.venv\Scripts\python.exe scripts/kd_bronze_cart_check.py
.\.venv\Scripts\python.exe scripts/kd_bronze_cart_wide.py
.\.venv\Scripts\python.exe scripts/kd_bronze_mlp_check.py
.\.venv\Scripts\python.exe scripts/kd_bronze_export.py
.\.venv\Scripts\python.exe scripts/kd_bronze_lr_portable.py
.\.venv\Scripts\python.exe scripts/kd_bronze_mlp_compression.py
.\.venv\Scripts\python.exe scripts/kd_bronze_export.py --finalize
.\.venv\Scripts\python.exe -m pytest -q tests/test_student.py tests/test_student_lightgbm.py tests/test_student_comparison.py tests/test_stacking.py
```

Cache nằm ở `data/interim/kd_bronze_research`. Chạy lại stage sẽ kiểm fingerprint của config, mã và tập fitting rồi bỏ qua checkpoint đã hoàn thành. Bảng `*_runs.csv` ghi từng fit. `*_oof.csv.gz` ghi ID, nhãn thật của hàng giữ lại, fold, seed, mode gián tiếp qua tên recipe và điểm thô. [Config](../configs/kd_bronze_research.json) · [Thư mục kết quả](tables/student_bronze_kd/) · [Manifest](tables/student_bronze_kd/research_manifest.json)

Tái sử dụng ba Teacher theo fold, bản đồ folds, nhãn mềm Gold/Silver đã kiểm tra và bộ trích E2 của dự án. **Điểm Teacher trên bronze, các lần fit Student, dự đoán, bootstrap, phép đo CPU và gói research là kết quả chạy mới.** [Dữ liệu đã lọc theo fold](tables/student_bronze_kd/data_preparation.json) · [Điểm Teacher bronze theo ID](tables/student_bronze_kd/teacher_bronze_scores.csv.gz)

## Các lượt thử bổ sung

- **Byte CNN, tăng ngân sách huấn luyện.** Trên cùng ba fold và các seed 202/303/404, cấu hình 1.536 bước đạt AP **0,85506** khi dùng KD và Bronze nhãn mềm, so với **0,84368** của hard-label. Chênh lệch **+0,01139 AP**, khoảng tin cậy 95% **[+0,00364, +0,01763]**, thắng **7/9 cặp fold–seed**. Bảng lưu cả đối chứng 384 bước và bốn cách học. [Cấu hình và bảng kết quả CNN](tables/student_bronze_kd_cnn_followup/) · [Runner CNN](../scripts/kd_bronze_cnn_budget.py)
- **Tiny MLP 32 nút và chi phí inference.** Thử score KD, mixed-logit, chỉ logit, thu nhỏ từ vựng, nén int8 và kiểm thêm LightGBM 100 cây. Mixed-logit đạt AP **0,91395** so với **0,91225** của Tiny MLP hard-label. Khoảng tin cậy của mức tăng cắt 0. [Báo cáo Tiny MLP](week7_tiny_mlp_tradeoff.md)

Các lượt trên thuộc research và dùng các fold development đã có. Mô hình đã chọn để Hy tích hợp được bàn giao ở PR Student Android. [Bàn giao MLP 64 nút](https://github.com/phuctran33/PhishGuardVN/blob/bc3a3a7054e2f6e6e733595f40f38439784536a1/docs/week7_android_mlp_handoff.md)
