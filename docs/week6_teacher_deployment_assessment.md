# Đánh giá triển khai Teacher v2 trên Android

**Ngày đánh giá (Status date):** 2026-11-15
**Phạm vi (Scope):** PhishGuardVN Week 6 — triển khai inference Teacher v2 đã đóng băng (frozen) trên Android
**Quyết định (Decision):** Tiếp tục sử dụng Dart-native inference path đã được xác minh làm triển khai hiện tại. Xem ONNX/TFLite là các công việc đánh giá trong tương lai, không phải các chuyển đổi đã hoàn thành.

## 1. Tóm tắt điều hành

Pipeline Teacher v2 đã đóng băng được export thành các artifacts có thể đọc bằng Dart và được tái tạo bởi triển khai Dart thông qua việc đối chiếu với Python reference fixture chính thức.

Đã xác minh trong môi trường phát triển hiện tại:

- Full Teacher artifact: `artifacts/teacher_v2_android/dart_teacher_v2_model.json`
- HistGradientBoosting export: 300 trees và 8,700 nodes.
- Golden reference fixture: 41 trường hợp URL hợp lệ.
- Dart test suite mới nhất: 294/294 tests passed.
- Full Teacher stage parity: 41/41 cases passed đối với SVM margin, HistGB raw score, HistGB probability, meta raw score, meta probability và final prediction.
- Sai khác số học lớn nhất được ghi nhận nằm ở mức sai số làm tròn dấu phẩy động (floating-point round-off), xấp xỉ `4e-15`, thấp hơn fixture tolerance `1e-6`.
- Threshold đã đóng băng: `0.6945740700635259`; quy tắc quyết định: `score >= threshold`.

Các kết quả này xác lập Python-to-Dart inference parity đối với những trường hợp fixture được cung cấp. Tuy nhiên, chúng không chứng minh hiệu năng trên thiết bị Android, khả năng chuyển đổi ONNX/TFLite, độ ổn định trong môi trường production hoặc chất lượng mô hình trên dữ liệu chưa từng xuất hiện (unseen data).

Meta score là một decision score chưa được hiệu chỉnh (uncalibrated decision score). Không được biểu diễn giá trị này dưới dạng xác suất hoặc phần trăm cho biết một URL là an toàn hay độc hại.

## 2. Đánh giá các phương án triển khai

### A. Dart-native inference — Phương án hiện được lựa chọn

**Trạng thái: Đã triển khai và kiểm thử parity với fixture 41 trường hợp hiện tại.**

Triển khai này sử dụng trực tiếp các SVM parameters, HistGB tree structures và meta Logistic Regression parameters đã export trong Dart. Phương án này không yêu cầu Python runtime trên thiết bị Android.

Ưu điểm:

- Offline inference mà không cần Python service.
- Triển khai hiện tại khớp với Python reference đã đóng băng trên toàn bộ 41 fixture cases.
- Không cần model conversion runtime.

Giới hạn và các nội dung cần xác minh thêm:

- Parity fixture có số lượng trường hợp hữu hạn và không chứng minh tính chính xác đối với mọi URL có thể xảy ra hoặc mọi trường hợp biên liên quan đến floating-point.
- Chưa benchmark Android device latency, memory usage, model loading/cold-start và APK/AAB size.
- Python batch input validation và Dart E2 URL parsing là hai contract riêng biệt. Không được đưa hành vi nghiêm ngặt của Python `validate_urls()` vào `E2Extractor`, vì điều đó sẽ phá vỡ Python URL-parser feature parity đã được thiết lập.
- Dart runtime vẫn cần một public inference input/error contract được tài liệu hóa và kiểm thử rõ ràng.
- Loader đã xác thực model schema và structural invariants, nhưng việc xác minh SHA-256 của toàn bộ artifact file với manifest tại runtime vẫn chưa được thiết lập.

### B. ONNX

**Trạng thái: Là một phương án tiềm năng; quá trình chuyển đổi end-to-end và thực thi trên Android CHƯA được xác minh.**

Pipeline bao gồm các nhóm estimator mà ONNX converter có thể hỗ trợ. Tuy nhiên, việc hỗ trợ các estimator hoặc operator riêng lẻ không chứng minh rằng pipeline đã được huấn luyện cụ thể này có thể chuyển đổi hoặc chạy với kết quả tương đương.

Trước khi tuyên bố hỗ trợ ONNX, cần thực hiện một đợt thử nghiệm độc lập (separate spike) với các bước sau:

1. Chuyển đổi chính xác các SVM, HistGB và meta stages đã được huấn luyện và đóng băng, bao gồm preprocessing/vectorization, mà không huấn luyện lại hoặc thay đổi features.
2. Ghi lại converter/runtime versions và các tùy chọn chuyển đổi (conversion options).
3. Chạy ONNX artifact đã export bằng Android ONNX Runtime package dự kiến sử dụng.
4. So sánh các intermediate stages và final scores với Python reference trên 41 golden cases và một bộ edge cases rộng hơn.
5. Xác minh threshold decisions, missing-value routing, Unicode/IDNA inputs và URL normalization behavior.
6. Đo lường Android latency, memory, startup cost và kích thước model/runtime sau khi đóng gói (packaged model/runtime size).

Cho đến khi tất cả các điều kiện kiểm tra trên đều đạt, ONNX chưa phải là định dạng triển khai đã được bàn giao hoặc xác minh. Triển khai Dart hiện tại vẫn là baseline.

### C. TensorFlow Lite (TFLite)

**Trạng thái: Chưa được đánh giá end-to-end; chưa có TFLite artifact hoặc runtime parity nào được xác minh.**

Sklearn stacking pipeline hiện tại không phải là TensorFlow model. Một phương án sử dụng TFLite sẽ cần thêm một quy trình chuyển đổi hoặc triển khai lại, đồng thời phải xử lý cẩn thận text vectorization, SVM margin calculation, HistGB tree traversal và meta scoring.

Không được tuyên bố khả năng tương thích với TFLite chỉ dựa trên việc Android hỗ trợ TFLite runtime. Chỉ nên đánh giá phương án này nếu có lý do cụ thể liên quan đến sản phẩm/runtime đủ thuyết phục để chấp nhận phần công việc chuyển đổi và parity verification bổ sung.

## 3. Các giới hạn đã biết và công việc chưa được giải quyết

1. **Phạm vi parity hữu hạn (Finite parity coverage):** 41 valid URL fixtures chỉ chứng minh implementation parity đối với những trường hợp này. Cần bổ sung adversarial cases và boundary cases trước khi đưa ra các tuyên bố rộng hơn về tính chính xác.

2. **Input contract:** Python `validate_urls()` xác thực một batch không rỗng và từ chối các giá trị không phải string, giá trị rỗng, NUL/control characters và whitespace ở đầu hoặc cuối chuỗi trước khi xây dựng feature-frame. Dart `E2Extractor` cố ý giữ nguyên Python URL-parser parity và không tương đương với batch validator nghiêm ngặt này. Vẫn cần xác định và kiểm thử một Dart inference validation API riêng biệt cùng với các quy tắc xử lý lỗi batch rõ ràng (explicit batch error semantics).

3. **Tính toàn vẹn của artifact (Artifact integrity):** Loader xác thực schema và model structure, bao gồm embedded source/reference metadata. Việc xác minh SHA-256 của toàn bộ exported artifact file với manifest tại runtime vẫn chưa được triển khai hoặc chứng minh.

4. **Xác minh Android runtime (Android runtime verification):** Bằng chứng parity hiện tại chưa bao gồm các kết quả đo lường latency, memory, cold-start hoặc package size trên thiết bị thực tế.

5. **Chất lượng mô hình và calibration (Model quality and calibration):** Meta score là một score chưa được hiệu chỉnh (uncalibrated score), được sử dụng cùng threshold đã đóng băng. Không được mô tả giá trị này dưới dạng xác suất phần trăm cho biết một URL là an toàn hay độc hại.

6. **Khả năng tổng quát hóa (Generalization):** Fixture parity là một bước kiểm tra tính tương đương của triển khai (implementation-equivalence check), không phải một đánh giá độc lập về chất lượng phát hiện phishing, false-positive rate hoặc hiệu năng trước các mối đe dọa trong tương lai.

7. **ONNX/TFLite:** Cả hai định dạng đều chưa được chuyển đổi và xác minh end-to-end đối với pipeline đã đóng băng cụ thể này.

8. **Student model:** Quá trình Student training/distillation và Student offline evaluation trong Week 7 là các công việc đã được lên kế hoạch, không phải công việc đã hoàn thành. Teacher đã đóng băng vẫn là nguồn cung cấp targets cho đến khi Student pipeline được xác minh độc lập.

## 4. Khuyến nghị release cho PR hiện tại

Giữ phạm vi PR ở mức hẹp:

- Bao gồm Dart-native Teacher implementation, exported frozen artifact, manifest update, golden fixture, tests, exporter update và tài liệu deployment/Week 7 nếu phù hợp với phạm vi PR.
- Trình bày kết quả đã xác minh một cách chính xác: lần chạy local mới nhất đã PASS 294 Dart tests và toàn bộ 41 full-pipeline fixture cases.
- Không tuyên bố hỗ trợ ONNX/TFLite, sẵn sàng về hiệu năng trên Android, hoàn thành Student hoặc có khả năng URL validation đạt tiêu chuẩn production-grade nếu các bước kiểm tra tương ứng chưa được thực hiện.
- Không đưa `.venv-teacher311/` vào version control.
- `scripts/append_full_teacher_export.py` không cần thiết cho các lần export có khả năng tái tạo thông thường nếu exporter chính đã chứa đầy đủ logic export. Không đưa helper này vào PR trừ khi có một mục đích sử dụng riêng biệt đã được tài liệu hóa.

## 5. Các bước tiếp theo được đề xuất

1. Xử lý phản hồi từ reviewer đối với Dart-native Teacher PR hiện tại.
2. Xác định và kiểm thử Dart inference input/error contract riêng biệt, không làm ảnh hưởng đến E2 parser parity.
3. Bổ sung runtime artifact file-integrity verification dựa trên manifest.
4. Chạy một bài kiểm tra offline smoke test tối thiểu trên thiết bị Android thực tế và ghi lại device/OS, latency, memory và artifact size.
5. Chỉ đánh giá ONNX dưới dạng một separate measured spike nếu phương án này mang lại lợi ích triển khai cụ thể.
6. Chỉ bắt đầu Week 7 Student training/distillation sau khi Teacher contract và target-generation path đã được đóng băng.
