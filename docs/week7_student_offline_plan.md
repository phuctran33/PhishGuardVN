# Kế hoạch triển khai Student Offline Inference cho Week 7

## 1. Trạng thái và phạm vi

**Trạng thái (Status):** Chỉ đang ở giai đoạn lập kế hoạch (planning only). Theo kế hoạch này, chưa có Student model nào được training, distillation, calibration hoặc phê duyệt để triển khai.

Teacher v2 bundle đã được promote, E2 feature formulas/order, frozen threshold và các released artifacts là những tài liệu tham chiếu bất biến (immutable references) cho công việc này. Các thử nghiệm Student không được training lại, ghi đè hoặc âm thầm sửa đổi Teacher.

Triển khai Dart full Teacher hiện tại đã vượt qua official parity fixture hiện có: 41/41 cases, trong một lần chạy Dart test đạt 294/294 tests passed. Điều này xác lập implementation parity trên fixture được cung cấp; tuy nhiên, không chứng minh chất lượng phát hiện trên dữ liệu chưa từng xuất hiện (unseen data) hoặc mức độ sẵn sàng cho production trên Android.

## 2. Mục tiêu

Week 7 cần tạo ra các kết quả sau:

1. Một quy trình tạo training dataset/target-generation có khả năng tái tạo (reproducible) và được kiểm soát rò rỉ dữ liệu (leakage-controlled).
2. Ít nhất một Student candidate có kích thước nhỏ gọn (compact) và một baseline được ghi nhận.
3. Một báo cáo đánh giá độc lập (independent evaluation report), so sánh Student outputs với cả Teacher targets và ground-truth labels hiện có.
4. Một báo cáo đánh giá tính khả thi của offline deployment trong môi trường Android mục tiêu.
5. Một khuyến nghị go/no-go rõ ràng. Việc tích hợp Student không tự động được thực hiện khi kết thúc tuần.

## 3. Kiểm soát dữ liệu và rò rỉ dữ liệu

1. **Đóng băng quy trình trước khi fitting (Freeze the protocol before fitting).** Ghi lại dataset version và hashes, eligible sample IDs, label provenance, grouping key, split boundaries, preprocessing, metrics và resource budgets.

2. **Thực hiện grouping trước khi splitting (Group before splitting).** Các URL trùng lặp và gần trùng lặp (duplicate và near-duplicate URLs), các domain có liên quan và những samples khác có chung leakage-control group đã chọn phải nằm trong cùng một split. Cần tài liệu hóa quy tắc grouping.

3. **Tách biệt train, validation và test (Separate train, validation, and test).** Sử dụng training data để fitting và tạo Teacher targets; sử dụng validation để lựa chọn model/threshold; dành riêng test cho một lần đánh giá cuối cùng sau khi model và decision policy đã được đóng băng.

4. **Không tuning trên test data (Do not tune on test data).** Không kiểm tra test labels hoặc Teacher scores để lựa chọn features, hyperparameters, thresholds hoặc model variants.

5. **Bảo vệ dữ liệu URL (Protect URL data).** Sử dụng local storage và access controls đã được phê duyệt. Khi có thể, lưu sample IDs và dataset/source hashes trong các báo cáo; không để lộ raw URLs trong logs hoặc reports trừ khi đã được phê duyệt rõ ràng.

## 4. Tạo Teacher targets

1. Chỉ sử dụng official `load_released_teacher` loader cùng với locked CPython 3.11 environment và released bundle đã được xác minh.

2. Xác minh bundle và reference hashes trước khi tạo targets. Ghi lại runtime/library versions và danh tính chính xác của Teacher artifact (exact Teacher artifact identity).

3. Chỉ tạo Teacher outputs cho các training samples đủ điều kiện (eligible training samples). Không tạo hoặc sử dụng Teacher outputs từ test set cho mục đích training hoặc tuning.

4. Ghi rõ định nghĩa target (target definition):

   - Teacher meta score là một score chưa được hiệu chỉnh (uncalibrated score), không phải xác suất cho biết URL an toàn hay độc hại.
   - Nếu lựa chọn soft-score distillation, phải giữ nguyên raw score và tài liệu hóa mọi phép biến đổi đã được phê duyệt.
   - Nếu lựa chọn hard labels, sử dụng frozen Teacher threshold và ghi rõ rằng phương pháp này loại bỏ thông tin về score.

5. Lưu sample IDs, target values, dataset version và source hashes. Không đưa raw URLs vào các target files được tạo ra, trừ khi điều đó là cần thiết và đã được phê duyệt.

6. Dừng target-generation job nếu đầu vào không hợp lệ hoặc xảy ra lỗi Teacher loading/inference; không được âm thầm loại bỏ hoặc gán lại nhãn cho các samples bị lỗi.

## 5. Student candidates và training

Bắt đầu bằng một baseline có khả năng tái tạo (reproducible baseline) trước khi thử nghiệm các model phức tạp hơn.

Các nhóm candidate có thể bao gồm:

- Một character/byte n-gram linear model có kích thước nhỏ gọn.
- Một character-level neural model nhỏ, chỉ khi kích thước và chi phí runtime của nó được chứng minh là hợp lý.

Đối với mỗi candidate, cần đóng băng và ghi nhận:

- Input canonicalization và cấu hình tokenizer/vectorizer.
- Model architecture và hyperparameters.
- Training seed và software/runtime versions.
- Training data IDs/split hash và Teacher target version.
- Model weights và artifact hash.

Không được âm thầm thay thế Teacher's E2 feature contract, thay đổi Teacher hoặc tuyên bố tính tương đương chỉ vì Student sử dụng các input features tương tự.

## 6. Quy trình đánh giá

Thực hiện đánh giá theo thứ tự sau:

1. Training diagnostics và các sanity checks cơ bản.
2. Group-held-out validation để lựa chọn model và decision policy.
3. Đóng băng Student artifact và toàn bộ decision settings.
4. Chạy test set chưa từng được sử dụng (untouched test set) một lần để lập báo cáo cuối cùng.

Báo cáo cả mức độ tương đồng với Teacher (Teacher agreement) và các task metrics dựa trên ground truth khi có labels:

- Score agreement/correlation với Teacher targets, nếu phù hợp.
- Hard-label agreement với frozen Teacher decision.
- Precision-recall metrics, bao gồm average precision.
- Recall và false-positive rate tại operating point đã chọn.
- Confusion matrix và các class-wise metrics.
- Kết quả riêng biệt cho các nhóm Unicode/IDNA, long URLs, IP hosts, malformed inputs và các edge-case slices khác đã được xác định.
- Calibration analysis nếu tạo ra probabilities; không được gọi raw Student hoặc Teacher scores là probabilities nếu chưa có bằng chứng về calibration.

Teacher agreement không thể thay thế cho ground-truth evaluation. Không được xem Student là tương đương chỉ vì aggregate accuracy hoặc Teacher agreement cao.

## 7. Tính khả thi của offline Android

Trên thiết bị Android và API range dự kiến sử dụng, cần đo lường và ghi nhận:

- Model/tokenizer asset size và mức độ ảnh hưởng đến tổng APK/AAB size.
- Peak memory trong quá trình load và inference.
- Cold-start/model-load time.
- Per-URL p50 và p95 inference latency.
- Battery/thermal behavior trong một workload thực hiện inference lặp lại đã được xác định.
- Khả năng hoạt động offline khi network access bị vô hiệu hóa.
- Hành vi xử lý đối với invalid, unsupported và non-classifiable inputs.
- Model version và hành vi xác minh asset integrity.

Ghi lại device model, Android version/API level, build mode, test workload, warm-up policy và measurement method. Không được suy luận hiệu năng trên thiết bị Android từ kết quả kiểm thử trên desktop.

## 8. Các điều kiện để release

Student không được tích hợp vào production Flutter path cho đến khi tất cả các điều kiện áp dụng sau đây đều đạt:

- Data provenance và split integrity của training data đã được review.
- Không phát hiện train/validation/test leakage.
- Teacher target-generation script và environment có khả năng tái tạo (reproducible).
- Student artifact, tokenizer/configuration, code và runtime versions đã được đóng băng và tạo hashes.
- Independent test metrics đáp ứng các acceptance criteria đã được product phê duyệt.
- Hành vi xử lý edge cases và invalid inputs đã được tài liệu hóa và kiểm thử.
- Các phép đo offline trên Android đáp ứng các giới hạn size, memory và latency đã được phê duyệt rõ ràng.
- Asset integrity/version checks và fallback/error behavior đã được triển khai.
- Security/privacy review và independent evaluation review đã hoàn tất.

Nếu acceptance criteria hoặc device budgets chưa được phê duyệt, hãy ghi nhận chúng là các quyết định còn bỏ ngỏ (open decisions) và không được tuyên bố Student đã sẵn sàng để release.

## 9. Các sản phẩm bàn giao và tiêu chí hoàn thành

Các kết quả dự kiến của Week 7:

1. Data/split manifest có version, kèm hashes và grouping rules.
2. Teacher-target generation script/configuration có khả năng tái tạo và run report.
3. Student baseline và các candidate training configurations.
4. Các candidate artifacts đã được đóng băng (frozen), kèm hashes.
5. Validation và final test evaluation report.
6. Android offline benchmark report.
7. Go/no-go recommendation và danh sách các rủi ro chưa được giải quyết (unresolved-risk list).

Week 7 chỉ được xem là hoàn thành khi các kết quả trên đã được review và quyết định go/no-go được ghi nhận. Chỉ tạo ra một model đã training là chưa đủ để được xem là hoàn thành.

## 10. Open decisions

- Student architecture được phép sử dụng và kích thước model/package tối đa.
- Android device/API range mục tiêu và các giới hạn latency/memory.
- Student sẽ dự đoán Teacher soft scores, hard labels hay một target riêng biệt đã được phê duyệt.
- Dataset version, group key, chính sách duplicate/near-duplicate detection và split ratios.
- Nguồn ground-truth labels và các yêu cầu về chất lượng labels.
- Các kỳ vọng về IDNA/UTS-46 compatibility và hành vi được chấp nhận đối với unsupported hosts.
- Các yêu cầu operating point về precision/recall và false-positive đã được product phê duyệt.
- Liệu Student candidate sẽ thay thế Teacher, hoạt động như một first-stage filter hay tiếp tục được giữ ở trạng thái thử nghiệm (experimental).

Kế hoạch này không đưa ra bất kỳ tuyên bố nào về Student training, Student parity, production readiness hoặc hiệu năng trên Android.