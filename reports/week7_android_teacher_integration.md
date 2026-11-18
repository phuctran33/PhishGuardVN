# Báo cáo tuần 7: tích hợp Teacher v2 offline trên Android (Issue #29)

**Trạng thái: Đã triển khai và kiểm thử chức năng Teacher UI trên Android emulator; chưa hoàn thành toàn bộ Issue #29 hoặc H7.4.**

Phần Dart/Flutter là cơ sở tích hợp Teacher v2. Đã có thêm bằng chứng Android runtime và offline smoke test trên emulator. Tuy nhiên, parity Python–Android trên thiết bị, benchmark hiệu năng và các kiểm thử artifact lỗi trên thiết bị vẫn chưa hoàn tất.

## 1. Phạm vi và nguyên tắc

- Giữ nguyên Teacher v2, threshold, E1/E2, thứ tự 20 đặc trưng, reference 45 brand và preprocessing đã nghiệm thu.
- Không dùng FastAPI hoặc mạng trong đường suy luận. Student chưa được xác minh nên không đưa vào app.
- Không thay đổi threshold, model hoặc decision rule.
- Không diễn giải model score thành xác suất an toàn hoặc phần trăm lừa đảo.

## 2. Tiến độ theo hạng mục

| Hạng mục | Trạng thái | Bằng chứng / lệnh | Ghi chú |
| --- | --- | --- | --- |
| Teacher loader, kiểm toàn vẹn artifact, bootstrap, UI | Đã triển khai và kiểm thử | `cd mobile/app && flutter analyze` và `flutter test` | Analyze: No issues found. Flutter tests: 46/46 passed |
| Teacher loader với artifact thật | Đã có test | `mobile/app/test/teacher_loader_test.dart` | Test đọc manifest và hai JSON artifact thật; kiểm tra thiếu file, JSON không hợp lệ, contract mismatch, SHA-256, kích thước và lỗi khởi tạo model |
| Input validation và UI states | Đã có test | `mobile/app/test/input_validation_test.dart`, `mobile/app/test/widget_test.dart` | Bao gồm input không hợp lệ, bootstrap retry và các trạng thái UI |
| Teacher prediction adapter | Đã triển khai và có test riêng | `mobile/app/lib/src/teacher_url_classifier.dart`, `mobile/app/test/teacher_prediction_test.dart` | Sử dụng API `finalScore`, `classId`, `threshold`; kiểm tra score hữu hạn, class ID hợp lệ, threshold và consistency với decision rule |
| Dart package tests | Chưa chạy lại trong đợt tích hợp này | `(cd mobile/packages/phishguard_features && dart test)` | Fixture và test Teacher v2 đã tồn tại; cần chạy lại để xác nhận riêng package tests |
| Teacher prediction parity với Python fixture | Đã chạy, đạt 41/41 trường hợp | `mobile/app/test/teacher_prediction_test.dart`, `mobile/packages/phishguard_features/test/fixtures/teacher_v2_pipeline_reference.json` | 25 phishing, 16 benign; đối chiếu final score với tolerance 1e-6, class ID, model version, threshold và decision rule trong Flutter test environment |
| Teacher UI trên Android emulator | Đã build, cài đặt và kiểm thử chức năng | `flutter run -d emulator-5554` | APK build và cài đặt thành công; app khởi tạo Teacher v2 và thực hiện phân loại URL trên emulator |
| Teacher model loading trên Android | Đã xác minh | Kết quả hiển thị trên app | Model `teacher-stacking-v2`; thời gian nạp 183 ms; tổng dung lượng JSON 2.547.394 byte |
| Android URL classification smoke test | Đạt 4/4 trường hợp mẫu | Kết quả hiển thị trực tiếp trên emulator | 1 benign và 3 phishing, chi tiết tại Section 3 |
| Input validation trên Android | Đã xác minh một trường hợp | URL `https://example.com:99999/` | UI trả `invalid_port`, không hiển thị label hoặc score |
| Android offline runtime smoke test | Đã xác minh trong một lượt thử thủ công | Tắt mạng emulator, xác nhận trình duyệt báo `No internet`, mở lại app và phân tích URL | Teacher vẫn trả kết quả inference, score 0.743917 |
| Trang parity Teacher độc lập trên thiết bị | Chưa triển khai | — | Không nhầm với trang E2 parity hiện có |
| Parity Python–Android trên thiết bị | Chưa xác minh | — | Kết quả 41/41 hiện tại là Teacher adapter parity trong Flutter test environment, chưa phải bằng chứng parity chạy trên Android emulator/thiết bị thật |
| Hiệu năng: cold-start, p50/p95, RAM, kích thước APK/asset | Chưa đo đầy đủ | — | Thời gian model loading 183 ms là số liệu quan sát trong app, không thay thế benchmark cold-start hoặc p50/p95 |

## 3. Android emulator smoke test

### 3.1. Môi trường kiểm thử

- Emulator: Pixel 6 AVD.
- Android: 15 / API 35.
- ABI: arm64-v8a.
- Flutter: 3.47.9.
- Dart: 3.13.7.
- Lệnh chạy: `flutter run -d emulator-5554`.
- APK debug build và cài đặt thành công trên emulator.

### 3.2. Teacher model loading

| Thuộc tính | Kết quả |
| --- | --- |
| Model version | `teacher-stacking-v2` |
| Threshold | `0.6945740700635259` |
| Decision rule | `score >= threshold` |
| Tổng thời gian nạp | 183 ms |
| Đọc artifact | 34 ms |
| Hash verification | 64 ms |
| Parse JSON | 41 ms |
| Khởi tạo model | 43 ms |
| Tổng dung lượng JSON | 2.547.394 byte |

### 3.3. URL classification

| URL kiểm thử | Kết quả kỳ vọng | Kết quả thực tế | Score | Đánh giá |
| --- | --- | --- | ---: | --- |
| `https://www.vietcombank.com.vn/vi-VN/` | Benign | Benign | 0.455156 | Đạt |
| `https://vietcombank.com.vn.xacminh-id.xyz/` | Phishing | Phishing | 0.990625 | Đạt |
| `https://vietcombnak.com/` | Phishing | Phishing | 0.880492 | Đạt |
| `https://vietc0mbank.top/` | Phishing | Phishing | 0.998609 | Đạt |

Kết quả: 4/4 trường hợp khớp với kỳ vọng kiểm thử.

Các score được so sánh với threshold `0.6945740700635259` theo decision rule `score >= threshold`. Score chưa được hiệu chuẩn và không được diễn giải thành phần trăm an toàn hoặc phần trăm lừa đảo.

### 3.4. Input validation

- Input: `https://example.com:99999/`.
- Kết quả: Không phân loại được.
- Error code: `invalid_port`.
- UI không hiển thị label hoặc score.
- Không tạo ra kết quả phân loại giả cho input không hợp lệ.

### 3.5. Offline runtime smoke test

- Tắt kết nối mạng trên emulator.
- Mở Google bằng trình duyệt trên emulator và xác nhận trạng thái `No internet`.
- Thoát ứng dụng, mở lại khi vẫn đang tắt mạng.
- Chọn URL `http://[2001:db8::1]/login`.
- Ứng dụng vẫn thực hiện inference và hiển thị:
  - Label: Phishing.
  - Score: `0.743917`.
  - Threshold: `0.6945740700635259`.
  - Model: `teacher-stacking-v2`.

Kết quả này xác nhận ứng dụng có thể khởi tạo Teacher model và phân tích URL trong lượt kiểm thử khi emulator không có Internet. URL không được truy cập trong quá trình phân tích.

Đây là smoke test thủ công trên emulator, chưa phải kiểm thử parity Python–Android hoặc benchmark hiệu năng.

## 4. Giới hạn đã biết

- Teacher adapter đã được đối chiếu với API thực tế của `TeacherV2Prediction`; sử dụng `finalScore`, `classId` và `threshold`, không còn giả định trường `score`.
- Adapter kiểm tra score hữu hạn, class ID hợp lệ, threshold khớp contract và class ID nhất quán với quy tắc `score >= threshold`.
- Flutter test environment có kết quả `46/46` tests passed; `flutter analyze` không còn issue.
- Teacher adapter parity với Python reference fixture đạt `41/41` trường hợp, gồm 25 phishing và 16 benign. Test đối chiếu final score với tolerance 1e-6, class ID, model version, threshold và decision rule.
- Kết quả 41/41 là bằng chứng parity của Teacher adapter trong Flutter test environment; chưa thay thế cho kiểm thử inference và parity trên Android emulator hoặc thiết bị thật.
- Dart package tests chưa được chạy lại trong đợt tích hợp này; cần chạy `(cd mobile/packages/phishguard_features && dart test)` để xác nhận riêng package.
- Đã có Android emulator smoke test cho 4 URL mẫu, một trường hợp invalid port và một lượt offline runtime test.
- Offline runtime test là kiểm thử thủ công trong một lượt chạy; cần bổ sung kiểm thử lặp lại và ghi nhận phương pháp kiểm tra mạng nếu cần mức bằng chứng cao hơn.
- Chưa có trang parity Teacher độc lập trên thiết bị; trang parity E2 hiện tại chỉ xác nhận extractor, không phải Teacher prediction.
- Manifest và model cùng nằm trong gói app: kiểm SHA-256 giúp phát hiện artifact bị hỏng hoặc lệch phiên bản, không chống được việc kẻ tấn công thay cả manifest và model.
- Parse khoảng 2,5 MB JSON trên luồng chính có thể ảnh hưởng thời gian khởi động. Thời gian model loading quan sát được là 183 ms trong lượt chạy này; chưa có benchmark cold-start có kiểm soát.
- Chưa có số liệu benchmark p50/p95 inference latency, RAM và kích thước APK/assets theo phương pháp đo thống nhất.
- Chưa kiểm thử đầy đủ trên Android runtime các tình huống thiếu asset, artifact không tương thích và lỗi khởi tạo model.
- Phiên Flutter debug đã có thông báo `Lost connection to device` ở cuối log sau khi build, cài đặt và chạy app. Cần phân biệt sự kiện mất kết nối debugger với trạng thái crash của ứng dụng; chưa có kết luận rằng ứng dụng bị crash.
- Vì parity Python–Android trên thiết bị và benchmark chưa hoàn thành, chưa kết luận H7.4 hoặc toàn bộ Issue #29 đã hoàn thành.

## 5. Definition of Done – H7.4 / Issue #29

- [x] Android runtime offline smoke test: Teacher chạy trên emulator trong lượt thử khi tắt mạng.
- [ ] Parity Python–Android cho Teacher: so score, label, threshold và decision rule với tham chiếu Python trên Android runtime.
- [ ] Số liệu hiệu năng đo thật: cold-start, p50/p95, RAM, kích thước APK và asset; ghi rõ thiết bị, Android, Flutter/Dart, số mẫu và phương pháp đo.
- [ ] Ca lỗi trên thiết bị: URL lỗi, thiếu asset, artifact không tương thích và lỗi khởi tạo model.

**Kết luận:** Phần review Android và tích hợp Teacher UI đã có bằng chứng triển khai, Flutter test và Android emulator smoke test. Có thể báo cáo hoàn thành mốc tích hợp Teacher UI. H7.4 và toàn bộ Issue #29 vẫn đang tiếp tục, chưa được đánh dấu hoàn thành.