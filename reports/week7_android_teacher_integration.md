# Báo cáo tuần 7: tích hợp Teacher v2 offline trên Android (Issue #29)

**Trạng thái: Teacher v2 và Student MLP int8 đã tích hợp vào Android; Flutter analysis/tests, asset verification và Profile APK build đều PASS. Teacher vẫn là classifier mặc định; Student ở trạng thái experimental. Chưa kết luận hoàn thành toàn bộ Issue #29 hoặc H7.4.**

Đã xác minh asset Teacher/Student bằng manifest SHA-256, chạy Flutter analyze và tests, đồng bộ assets thành công, và build APK Profile. Android runtime QA bao gồm classification, invalid URL/error handling và offline smoke test. Benchmark latency/RAM/APK có số liệu sơ bộ; giới hạn môi trường emulator và phương pháp đo được ghi rõ ở các phần sau.

## 1. Phạm vi và nguyên tắc

- Giữ nguyên Teacher v2, threshold, E1/E2, thứ tự 20 đặc trưng, reference 45 brand và preprocessing đã nghiệm thu.
- Teacher v2 vẫn là classifier chính/default. Student MLP int8 chỉ là experimental, không thay Teacher.
- Không dùng FastAPI hoặc mạng trong đường suy luận offline.
- Không thay đổi threshold, model hoặc decision rule trong đợt sửa review này.
- Không diễn giải model score thành xác suất an toàn hoặc phần trăm lừa đảo.

## 2. Tiến độ theo hạng mục

| Hạng mục | Trạng thái | Bằng chứng / lệnh | Ghi chú |
| --- | --- | --- | --- |
| Teacher loader, kiểm toàn vẹn artifact, bootstrap, UI | PASS | `cd mobile/app && flutter analyze`; `flutter test` | Analyze: không có issue; Flutter tests: 57/57 passed |
| Teacher loader với artifact thật | PASS | `mobile/app/test/teacher_loader_test.dart` | Kiểm tra manifest, JSON artifacts, file thiếu, JSON không hợp lệ, contract mismatch, SHA-256, kích thước và lỗi khởi tạo model |
| Input validation và UI states | PASS | `mobile/app/test/input_validation_test.dart`, `mobile/app/test/widget_test.dart` | Bao gồm input không hợp lệ, bootstrap retry và các trạng thái UI |
| Teacher prediction adapter | PASS | `mobile/app/lib/src/teacher_url_classifier.dart`; `mobile/app/test/teacher_prediction_test.dart` | Kiểm tra score hữu hạn, class ID, threshold và consistency với decision rule |
| Teacher prediction parity với Python fixture | PASS: 41/41 | `mobile/app/test/teacher_prediction_test.dart`; `teacher_v2_pipeline_reference.json` | 25 phishing, 16 benign; đối chiếu final score với tolerance 1e-6, class ID, model version, threshold và decision rule trong Flutter test environment |
| Student MLP int8 integration | Đã tích hợp; experimental | Student model `student-mlp-kd-int8-v1`; threshold `0.72961075` | Không thay Teacher làm classifier mặc định; score Student chưa calibrated |
| Student parity và rejected-input QA | Đã được kiểm tra độc lập | QA của Khiêm: 54 URLs và 9 trường hợp rejected | Ghi nhận là QA Student; không gộp vào kết quả Teacher parity 41/41 |
| Student error UI | PASS sau khi sửa | Android smoke test với URL port không hợp lệ | App hiển thị `Student không phân loại được`, thông báo `invalid_url` và mã lỗi |
| Android offline smoke test | Đã xác minh | Android emulator, Teacher và Student | Đường suy luận offline; không yêu cầu FastAPI hoặc kết nối mạng để phân loại |
| Asset sync và SHA-256 | PASS | `bash mobile/tool/sync_assets.sh` | Student artifacts hiện được lấy từ PR #35 fallback vì chưa có đủ artifacts trong repo; Student model và PSL được xác minh |
| Dart package tests | Chưa chạy lại | `(cd mobile/packages/phishguard_features && dart test)` | Cần chạy riêng nếu muốn xác nhận package-level tests |
| Android Profile APK | PASS | `cd mobile/app && flutter build apk --profile` | Build thành công: `build/app/outputs/flutter-apk/app-profile.apk`, 71.9 MB |
| Android latency/RAM benchmark | Có số liệu sơ bộ | Pixel 6 AVD, Android 15/API 35, arm64 | Số liệu emulator; RAM là PSS/RSS toàn app, không phải riêng Student; không đại diện thiết bị vật lý |

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

- Teacher v2 vẫn là classifier mặc định. Student MLP int8 chỉ là experimental, không thay thế Teacher.
- Student model version: `student-mlp-kd-int8-v1`; threshold: `0.72961075`. Student score chưa calibrated, không được diễn giải thành xác suất.
- Teacher adapter sử dụng `finalScore`, `classId` và `threshold`; kiểm tra score hữu hạn, class ID hợp lệ, threshold khớp contract và consistency với decision rule.
- Flutter analysis: không có issue. Flutter tests: `57/57` passed.
- Teacher adapter parity với Python reference fixture đạt `41/41` trường hợp, gồm 25 phishing và 16 benign. Test đối chiếu final score với tolerance 1e-6, class ID, model version, threshold và decision rule trong Flutter test environment.
- Student QA độc lập của Khiêm bao gồm 54 URLs và 9 trường hợp rejected. Không gộp kết quả này với Teacher parity 41/41.
- Android emulator đã được smoke test với Teacher và Student; có kiểm tra offline. Trường hợp Student URL port không hợp lệ hiện hiển thị error state `invalid_url` thay vì im lặng không có kết quả.
- Asset sync đã chạy thành công. Ở trạng thái hiện tại, Student artifacts chưa có đủ trong repo nên script dùng PR #35 làm fallback; SHA-256 của Student model và PSL đã được xác minh. Cần kiểm tra lại nhánh lấy artifacts trực tiếp từ repo sau khi PR #35 được merge.
- Dart package tests chưa được chạy lại trong đợt tích hợp này; cần chạy `(cd mobile/packages/phishguard_features && dart test)` để xác nhận riêng package.
- Teacher adapter parity 41/41 là bằng chứng trong Flutter test environment; không thay thế cho parity Python–Android trên Android runtime.
- Benchmark sơ bộ trên Pixel 6 AVD, Android 15/API 35, arm64:
  - Student benign: p50 0.036 ms, p95 0.059 ms.
  - Student phishing: p50 0.318 ms, p95 1.063 ms.
  - Teacher benign: p50 0.102 ms, p95 0.460 ms.
  - Teacher phishing: p50 0.195 ms, p95 0.904 ms.
  - RAM quan sát ở mức toàn app: PSS khoảng 118.5 MiB, RSS khoảng 212.4 MiB; không phải RAM riêng của Student.
- Các số liệu latency/RAM trên là kết quả emulator, không đại diện hiệu năng hoặc bộ nhớ trên thiết bị Android vật lý. Chưa có benchmark cold-start có kiểm soát trên thiết bị thật.
- Profile APK build thành công, kích thước 71.9 MB. Không so sánh trực tiếp với APK khoảng 26.3 MB từ lần build trước vì chưa xác nhận cùng build type và cấu hình.
- Manifest và model cùng nằm trong gói app: kiểm SHA-256 giúp phát hiện artifact bị hỏng hoặc lệch phiên bản, không chống được việc kẻ tấn công thay cả manifest và model.
- Parse khoảng 2,5 MB JSON có thể ảnh hưởng thời gian khởi động. Thời gian Teacher model loading 183 ms là quan sát trong một lượt chạy, chưa phải cold-start benchmark có kiểm soát.
- Chưa kiểm thử đầy đủ trên Android runtime các tình huống thiếu asset, artifact không tương thích và lỗi khởi tạo model.
- Phiên Flutter debug từng có thông báo `Lost connection to device` ở cuối log sau khi build, cài đặt và chạy app. Cần phân biệt sự kiện mất kết nối debugger với trạng thái crash của ứng dụng; chưa có kết luận rằng ứng dụng bị crash.
- Vì chưa có Teacher parity Python–Android đầy đủ trên Android runtime và chưa có benchmark thiết bị vật lý, chưa kết luận H7.4 hoặc toàn bộ Issue #29 đã hoàn thành.

## 5. Definition of Done – H7.4 / Issue #29

- [x] Android runtime offline smoke test: Teacher và Student đã được smoke test trên emulator trong lượt thử offline.
- [x] Flutter analysis và tests: analyze không có issue; 57/57 tests passed.
- [x] Teacher adapter parity với Python reference fixture trong Flutter test environment: 41/41.
- [x] Student QA độc lập: 54 URLs và 9 trường hợp rejected theo kết quả kiểm tra của Khiêm.
- [x] Student invalid URL error UI: hiển thị rõ `invalid_url` và mã lỗi.
- [x] Asset sync và SHA-256 verification: thành công với artifacts hiện có và PR #35 fallback.
- [x] Android Profile APK: build thành công, 71.9 MB.
- [ ] Kiểm thử clean clone không có PR #35 remote ref, sau khi Student artifacts đã có trong repo.
- [ ] Parity Python–Android đầy đủ cho Teacher trên Android runtime: so score, label, threshold và decision rule với tham chiếu Python.
- [ ] Benchmark chuẩn hóa trên thiết bị Android vật lý: cold-start, p50/p95, RAM, kích thước APK và asset; ghi rõ thiết bị, Android, Flutter/Dart, số mẫu và phương pháp đo.
- [ ] Ca lỗi trên Android runtime: thiếu asset, artifact không tương thích và lỗi khởi tạo model.
- [ ] Chạy lại Dart package tests riêng.
- [ ] Khiêm recheck regression trên PR head mới và xác nhận review; kiểm tra CI/review trước khi merge.

**Kết luận:** Teacher v2 và Student MLP int8 đã được tích hợp vào Android; Teacher vẫn là classifier mặc định, Student chỉ ở trạng thái experimental. Flutter checks, asset sync, Android emulator smoke tests và Profile APK build đã có kết quả. Benchmark hiện tại chỉ là số liệu sơ bộ trên emulator. H7.4 và toàn bộ Issue #29 chưa được đánh dấu hoàn thành cho đến khi các mục còn mở được xác minh.
