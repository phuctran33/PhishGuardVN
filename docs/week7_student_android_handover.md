# Week 7 — Student MLP int8 Android Handover

**Issue:** #29 — Android Teacher Offline Inference + Student Integration + Performance  
**Người phụ trách:** Hy  
**Người triển khai và kiểm thử Student:** Khiêm

> **Trạng thái hiện tại:** Student MLP int8 đã được tích hợp vào Android ở chế độ experimental. Teacher v2 vẫn là classifier mặc định. Không tự động chuyển Student thành classifier chính.

---

## 1. Mục tiêu và phạm vi

Tài liệu này hướng dẫn tích hợp, kiểm thử và bàn giao Student MLP KD int8 trên Flutter Android.

Mục tiêu:

1. Đọc và xác minh đúng Student artifacts.
2. Bảo toàn model version, threshold và decision rule.
3. Kiểm thử Student prediction và đối chiếu Python reference.
4. Xác minh Student hoạt động trong Android runtime.
5. Kiểm tra offline và error handling.
6. Ghi nhận latency, RAM, APK size và giới hạn kiểm thử.

### 1.1. Kiến trúc hiện tại

- Teacher v2 tiếp tục là classifier mặc định.
- Student MLP int8 là mô hình experimental.
- Student không tự động thay thế Teacher.
- Student inference không phụ thuộc FastAPI hoặc kết nối Internet.
- Không tự ý thay đổi model, threshold hoặc decision rule.
- Không diễn giải raw score thành xác suất an toàn hoặc phần trăm lừa đảo.

### 1.2. Môi trường kiểm thử

| Môi trường | Phạm vi xác minh |
|---|---|
| Laptop — Dart/Flutter tests | Model loader, validation, prediction, error handling và test fixtures |
| Android Emulator | Android build, cài đặt, model loading, inference runtime, offline và UI |
| Điện thoại Android thật | Xác minh bổ sung về phần cứng, RAM, latency và tương thích thực tế |

Có thể thực hiện phần lớn công việc trên laptop và Android Emulator. Nếu chưa có điện thoại thật, phải ghi rõ physical-device validation chưa thực hiện.

---

## 2. Model contract

### 2.1. Student MLP int8

| Thuộc tính | Giá trị |
|---|---|
| Model version | `student-mlp-kd-int8-v1` |
| Threshold | `0.72961075` |
| Decision rule | `score >= threshold` |
| Calibration | Chưa calibrated |
| Trạng thái | Experimental |
| Classifier mặc định | Teacher v2 |

Lưu ý:

- Không thay threshold `0.72961075` trong quá trình tích hợp.
- Không tự ý thay đổi model weights hoặc decision rule.
- Student score chưa calibrated, không được hiển thị như xác suất chắc chắn URL là phishing.
- Không dùng kết quả Student để thay thế kết quả Teacher mặc định.
- Khi model version hoặc threshold không khớp manifest/contract, phải xử lý như lỗi tương thích, không âm thầm tiếp tục inference.

### 2.2. Teacher v2

Teacher v2 vẫn là classifier chính:

| Thuộc tính | Giá trị |
|---|---|
| Model version | `teacher-stacking-v2` |
| Threshold | `0.6945740700635259` |
| Decision rule | `score >= threshold` |
| Vai trò | Default classifier |

Không thay đổi Teacher model, threshold, E1/E2, thứ tự 20 đặc trưng, reference 45 brand hoặc preprocessing đã nghiệm thu trong phạm vi bàn giao Student.

---

## 3. Student artifacts và asset synchronization

### 3.1. Artifacts nguồn

Thư mục artifacts Student Android hiện tại:

`artifacts/student_mlp_android/`

Các file chính:

| File | Vai trò |
|---|---|
| `manifest.json` | Model metadata, version, threshold, file size và SHA-256 |
| `student_mlp.json.gz` | Student MLP int8 model artifact |

Runtime assets trong Flutter app:

| File | Vai trò |
|---|---|
| `mobile/app/assets/student_mlp_manifest.json` | Manifest được đóng gói cho Android |
| `mobile/app/assets/student_mlp.json.gz` | Student model được đóng gói cho Android |

Không sử dụng artifacts LightGBM cũ thay cho hai Student artifacts hiện tại.

### 3.2. Đồng bộ assets

Chạy từ repository root:

```bash
bash mobile/tool/sync_assets.sh
```

Nguyên tắc của script:

1. Ưu tiên Student artifacts đã có trong repository.
2. Chỉ sử dụng PR #35 remote ref làm fallback khi artifacts trong repository chưa đầy đủ.
3. Copy artifacts vào đúng Flutter assets directory.
4. Xác minh SHA-256 và kích thước theo manifest.
5. Dừng nếu artifact không hợp lệ hoặc không khớp manifest.

**Trạng thái QA đã ghi nhận:** Asset sync thành công; lần chạy hiện tại sử dụng PR #35 fallback vì Student artifacts chưa đầy đủ trong repository. Student model và PSL đã được xác minh SHA-256.

### 3.3. Clean clone verification

Sau khi PR #35 được merge và Student artifacts có trong repository:

- [ ] Clone repository mới.
- [ ] Không fetch hoặc tạo PR #35 remote ref.
- [ ] Chạy `mobile/tool/sync_assets.sh`.
- [ ] Xác nhận script lấy artifacts trực tiếp từ repository.
- [ ] Xác minh SHA-256 và file size.
- [ ] Chạy Flutter tests và build APK.

Không đánh dấu clean clone verification là PASS chỉ dựa trên lần asset sync sử dụng PR #35 fallback.

---

## 4. Quy trình kiểm thử

### Bước 1 — Kiểm tra môi trường

Kiểm tra Flutter và Android devices:

```bash
flutter doctor -v
flutter devices
```

Xác nhận Flutter SDK, Dart SDK, Android SDK và Emulator sẵn sàng.

### Bước 2 — Đồng bộ và kiểm tra artifacts

```bash
bash mobile/tool/sync_assets.sh
```

Kiểm tra:

- Student manifest tồn tại.
- Student model tồn tại.
- Model version đúng `student-mlp-kd-int8-v1`.
- Threshold đúng `0.72961075`.
- SHA-256 và file size khớp manifest.
- Không sử dụng nhầm artifacts LightGBM cũ.

### Bước 3 — Kiểm tra Flutter app

Từ thư mục `mobile/app`:

```bash
flutter analyze
flutter test
```

Kết quả đã ghi nhận:

- Flutter analyze: không có issue.
- Flutter tests: 57/57 passed.
- Teacher adapter parity: 41/41 trong Flutter test environment.

Lưu ý: Teacher parity 41/41 không phải Student parity. Không gộp hai kết quả.

### Bước 4 — Student parity và rejected-input QA

Dùng Student Python reference và bộ fixtures tương ứng để đối chiếu Student.

Các nội dung cần ghi nhận:

- Số URL hợp lệ được kiểm tra.
- Số rejected inputs.
- Số trường hợp prediction khớp.
- Sai khác score và label nếu có.
- Model version, threshold và decision rule.
- Các lỗi chưa xử lý được.

QA độc lập của Khiêm đã ghi nhận:

- 54 URLs.
- 9 trường hợp rejected.

Đây là kết quả QA Student độc lập, không phải Teacher parity 41/41.

Không dùng kết quả E2 extractor parity hoặc Teacher parity để tuyên bố Student parity đạt.

### Bước 5 — Android Emulator runtime

Chạy ứng dụng trên Android Emulator:

```bash
cd mobile/app
flutter devices
flutter run -d <emulator_device_id>
```

Kiểm tra:

- App build và khởi chạy thành công.
- Student assets được đọc đúng.
- Student model load thành công.
- Student inference chạy trực tiếp trong Android runtime.
- UI hiển thị đúng label, score, threshold và model version.
- Invalid input hiển thị error state rõ ràng.

Student model hiện tại phải được hiển thị là experimental; không thay đổi classifier mặc định.

### Bước 6 — Offline smoke test

Trên Android Emulator:

1. Khởi chạy ứng dụng và xác nhận model đã load.
2. Tắt kết nối mạng hoặc bật Airplane Mode.
3. Đóng và mở lại ứng dụng khi vẫn offline.
4. Chạy thử URL hợp lệ.
5. Xác nhận Student inference vẫn hoạt động.
6. Ghi nhận kết quả và lỗi nếu có.

Offline smoke test xác minh khả năng chạy không cần Internet. Nó không thay thế prediction parity.

### Bước 7 — Input validation và error handling

Các trường hợp cần kiểm tra:

| Tình huống | Kết quả mong muốn |
|---|---|
| URL hợp lệ | Thực hiện inference |
| URL không hợp lệ | Hiển thị lỗi input |
| Port không hợp lệ | Reject, không tạo prediction |
| Thiếu Student model asset | Báo lỗi load model |
| Manifest không hợp lệ | Reject |
| SHA-256 mismatch | Reject |
| Model version không tương thích | Báo lỗi contract |
| Model initialization thất bại | Báo lỗi rõ ràng |
| Inference thất bại | Không fallback thành benign |

Student invalid URL UI đã được sửa. Với URL kiểm thử `https://example.com:99999/`, app hiển thị:

```text
Student không phân loại được
Không phân tích được URL (invalid_url).
Mã lỗi: invalid_url
```

Không chuyển lỗi validation, loading hoặc inference thành kết quả benign mặc định.

### Bước 8 — Android runtime parity

Đây là bằng chứng riêng với Flutter/Dart unit tests.

Để xác nhận Android runtime parity đầy đủ, cần:

1. Dùng cùng Python reference fixtures.
2. Chạy inference trực tiếp trên Android.
3. Thu thập score, label, threshold và model version.
4. Đối chiếu với Python reference.
5. Báo cáo số case pass/fail và sai khác lớn nhất.

Không tuyên bố Android runtime parity hoàn tất chỉ dựa trên việc APK build thành công hoặc Flutter tests passed.

---

## 5. Performance testing

Chỉ kết luận benchmark khi ghi rõ môi trường và phương pháp đo.

Các chỉ số cần theo dõi:

| Chỉ số | Nội dung |
|---|---|
| Cold-start | Thời gian từ lúc khởi chạy đến khi model sẵn sàng |
| Model loading | Thời gian đọc và khởi tạo artifacts |
| p50 inference | Median inference latency |
| p95 inference | 95th percentile inference latency |
| RAM | PSS/RSS khi load và inference |
| APK size | Kích thước APK theo build type |
| Student assets size | Kích thước Student artifacts được đóng gói |

### 5.1. Benchmark sơ bộ đã ghi nhận

Môi trường:

- Pixel 6 AVD.
- Android 15 / API 35.
- ABI arm64.

| Model / nhóm URL | p50 | p95 |
|---|---:|---:|
| Student benign | 0.036 ms | 0.059 ms |
| Student phishing | 0.318 ms | 1.063 ms |
| Teacher benign | 0.102 ms | 0.460 ms |
| Teacher phishing | 0.195 ms | 0.904 ms |

RAM toàn app:

- PSS khoảng 118.5 MiB.
- RSS khoảng 212.4 MiB.

Đây là số liệu toàn app, không phải RAM riêng Student.

Profile APK build đã thành công:

`build/app/outputs/flutter-apk/app-profile.apk`

Kích thước: 71.9 MB.

Không so sánh trực tiếp với APK khoảng 26.3 MB từ lần build trước vì chưa xác nhận cùng build type và cấu hình.

### 5.2. Giới hạn benchmark

- Số liệu hiện tại là benchmark sơ bộ trên Emulator.
- Chưa có benchmark chuẩn hóa trên điện thoại Android thật.
- RAM là số liệu toàn app.
- Không dùng thời gian Dart VM trên laptop thay cho Android runtime benchmark.
- Phải tách cold-start khỏi inference latency.
- Không ghi số liệu ước lượng thành kết quả đo thực tế.

---

## 6. Báo cáo kết quả và giới hạn

Báo cáo tích hợp hiện tại:

`reports/week7_android_teacher_integration.md`

Báo cáo cần phân biệt rõ:

| Loại kiểm thử | Xác minh điều gì? |
|---|---|
| E2 extractor parity | E2 feature extraction |
| Teacher v2 parity | Teacher inference |
| Student QA | Student prediction và rejected inputs |
| Student Android runtime smoke test | Student inference trên Android |
| Offline smoke test | Khả năng chạy không cần Internet |
| Performance benchmark | Latency, RAM và APK size |

### 6.1. Các giới hạn còn mở

- Clean clone chưa được xác minh khi không có PR #35 remote ref.
- Chưa có Teacher Python–Android parity đầy đủ trên Android runtime.
- Chưa có benchmark chuẩn hóa trên thiết bị Android vật lý.
- Chưa kiểm thử đầy đủ trên Android runtime các trường hợp thiếu asset, artifact không tương thích và lỗi khởi tạo model.
- Dart package tests chưa chạy lại trong đợt tích hợp này.
- Cần Khiêm recheck regression trên PR head mới và xác nhận review.

Không kết luận toàn bộ Issue #29 hoặc H7.4 hoàn thành khi các mục bắt buộc còn mở.

---

## 7. Definition of Done

### Student integration và QA

- [x] Student MLP int8 đã được tích hợp vào Android.
- [x] Student model version và threshold được xác định.
- [x] Student QA độc lập: 54 URLs và 9 rejected inputs.
- [x] Student invalid URL error UI đã được sửa.
- [x] Student offline smoke test đã được thực hiện.
- [x] Asset sync và SHA-256 verification thành công trong môi trường hiện tại.

### Flutter và Android

- [x] Flutter analyze không có issue.
- [x] Flutter tests: 57/57 passed.
- [x] Teacher adapter parity: 41/41 trong Flutter test environment.
- [x] Android Profile APK build thành công.
- [ ] Clean clone sync không cần PR #35 remote ref.
- [ ] Hoàn tất các kiểm thử Android runtime parity còn thiếu.
- [ ] Kiểm thử đầy đủ lỗi thiếu asset, artifact không tương thích và model initialization failure.
- [ ] Chạy lại Dart package tests riêng.

### Performance và bàn giao

- [x] Có benchmark sơ bộ trên Pixel 6 AVD.
- [x] Có số liệu RAM toàn app.
- [x] Có Profile APK size.
- [ ] Benchmark chuẩn hóa trên thiết bị Android vật lý.
- [ ] Khiêm recheck regression trên PR head mới.
- [ ] Khiêm xác nhận review/approve.
- [ ] Kiểm tra CI và review trước khi merge.

### Kiến trúc

- [x] Teacher v2 vẫn là classifier mặc định.
- [x] Student MLP int8 chỉ ở trạng thái experimental.
- [x] Không tự động thay Teacher bằng Student.
- [x] Không thay đổi Teacher model, threshold hoặc E2 contract trong phạm vi bàn giao này.

---

## 8. Tài liệu lịch sử — Student LightGBM KD

Phần này chỉ lưu bối cảnh của pipeline Student LightGBM cũ, không phải hướng dẫn triển khai Android hiện tại.

Các thông tin cũ gồm:

- Model: Student LightGBM KD.
- Mode: `kd_mixed`.
- Threshold cũ: `0.6204500086017339`.
- Tree count: 400.
- Artifacts cũ: `artifacts/student_lightgbm/`.
- Files cũ: `kd_mixed.json`, `hard_only.json`, `features.json`.
- Python reference cũ: `scripts/predict_lightgbm_student.py`.

Không sử dụng threshold, model JSON, TF-IDF pipeline, vocabulary/IDF hoặc tree evaluator của LightGBM cũ cho Student MLP int8.

Student hiện tại sử dụng:

- Model version: `student-mlp-kd-int8-v1`.
- Threshold: `0.72961075`.
- Artifacts: `artifacts/student_mlp_android/`.
- Runtime assets: `mobile/app/assets/student_mlp_manifest.json` và `mobile/app/assets/student_mlp.json.gz`.

Nếu cần tái hiện nghiên cứu LightGBM, tham khảo lịch sử Git và các artifacts cũ. Không trộn hai pipeline trong cùng runtime.

---

**Kết luận:** Student MLP int8 là mô hình experimental đã được tích hợp và có kết quả QA Android ban đầu. Teacher v2 tiếp tục là classifier mặc định. Các bước clean clone, một số kiểm thử runtime, physical-device benchmark và review regression vẫn cần hoàn tất trước khi kết luận toàn bộ Issue #29/H7.4 đã hoàn thành.