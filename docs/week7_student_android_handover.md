# Week 7 — Student Android Integration & Testing Guide

**Issue:** #29 — Android Teacher Offline Inference + Student Integration + Performance  
**Người phụ trách:** Hy  
**Người triển khai và kiểm thử Student:** Khiêm  

---

## 1. Mục tiêu và phạm vi

Tài liệu này hướng dẫn tích hợp và kiểm thử mô hình Student LightGBM KD trên Flutter Android.

Mục tiêu là xác minh Student:

1. Đọc và nạp đúng model artifacts.
2. Trích xuất features giống Python reference.
3. Cho kết quả inference tương đương Python.
4. Chạy được trong Android runtime.
5. Hoạt động khi không có kết nối Internet.
6. Có kết quả đo hiệu năng và báo cáo kiểm thử.

### Có bắt buộc phải có điện thoại Android thật không?

**Không cần nha, có thể thực hiện phần lớn công việc trên laptop bằng Dart/Flutter và Android Emulator.**

Phân biệt ba môi trường:

| Môi trường | Có thể kiểm thử |
|---|---|
| Laptop — Dart/Flutter tests | Model loader, feature extraction, prediction parity, validation, error handling |
| Android Emulator | Android build, cài đặt, inference runtime, offline, UI và performance sơ bộ |
| Điện thoại Android thật | Xác minh bổ sung về phần cứng, RAM, latency và tương thích thực tế |

Có thể bắt đầu và hoàn thành phần kiểm thử Emulator mà không cần chờ điện thoại thật. Nếu chưa có thiết bị thật, phải ghi rõ physical-device validation chưa thực hiện.

### Phạm vi kiến trúc

- Teacher v2 tiếp tục là engine mặc định.
- Student KD là mô hình thử nghiệm, chưa được xác minh Android.
- Tích hợp Student thành adapter/luồng riêng để kiểm thử.
- Không tự ý thay Student thành engine mặc định.
- Không thay đổi Teacher model, threshold, decision rule hoặc E2 contract.
- Student inference không được phụ thuộc API hoặc kết nối Internet.

---

## 2. Chuẩn bị môi trường kiểm thử

### 2.1. Công cụ cần có

- Python environment của repository.
- Flutter SDK và Dart SDK.
- Android Studio.
- Android SDK và Android Emulator.
- Git branch làm việc có các Student artifacts.

Kiểm tra môi trường từ thư mục gốc repository:

```bash
flutter doctor -v
flutter devices
```

Nếu chưa có Emulator, tạo Android Virtual Device (AVD) trong Android Studio.

Nên ưu tiên cấu hình Android Emulator tương đương môi trường đã dùng trong các kiểm thử Android trước đây nếu máy laptop đáp ứng được.

### 2.2. Kiểm tra Python reference

Chạy Student reference CLI:

```bash
python scripts/predict_lightgbm_student.py --examples
```

Có thể kiểm tra riêng hard-only để đối chiếu nghiên cứu:

```bash
python scripts/predict_lightgbm_student.py --mode hard_only example.com
```

Xác nhận Python reference chạy được trước khi triển khai Dart adapter.

Không huấn luyện lại model hoặc thay đổi threshold trong quá trình tích hợp Android.

---

## 3. Student artifacts và contract cần bảo toàn

### 3.1. Các artifact cần dùng

Thư mục:

```text
artifacts/student_lightgbm/
```

| File | Vai trò |
|---|---|
| `manifest.json` | Model metadata, hash, threshold, selected mode |
| `features.json` | Vocabulary, IDF, n-gram configuration và feature order |
| `kd_mixed.json` | Student KD model được chọn |
| `brand_reference_v1.csv` | Brand reference data |
| PSL asset | Public Suffix List |
| `hard_only.json` | Model hard-label dùng để đối chiếu, không phải model mặc định |

`*.model.txt` là native LightGBM format, không cần đóng gói đồng thời nếu Android sử dụng JSON model.

`python_reference.json` phục vụ kiểm thử đối chiếu, không phải runtime inference asset bắt buộc.

Ưu tiên dùng `kd_mixed.json` theo `selected_mode` trong manifest. Không tự ý chuyển sang `hard_only.json`.

### 3.2. Model contract

| Thuộc tính | Giá trị |
|---|---|
| Model | LightGBM Student KD |
| Mode | `kd_mixed` |
| Threshold | `0.6204500086017339` |
| Tree count | 400 |
| Seed | 42 |
| Objective | `cross_entropy` |
| Class 0 | benign |
| Class 1 | phishing |
| Decision rule | `score >= threshold` |
| Calibration | Chưa calibrated |
| Android verification | Chưa xác minh |

Lưu ý:

- Leaf values trong JSON đã bao gồm shrinkage và initial score.
- Không nhân learning rate thêm một lần nữa.
- Inference cộng leaf values của các cây rồi áp dụng sigmoid.
- Không tự ý thay đổi threshold, weights hoặc model JSON.
- Raw score chưa calibrated, không được hiển thị như phần trăm an toàn hoặc xác suất chắc chắn URL là phishing.

### 3.3. Feature extraction contract

Student inference cần giữ đúng thứ tự:

1. Nhận raw URL.
2. Validate URL.
3. Canonicalize URL tương đương Python `canonical_url`.
4. Chuẩn hóa text tương đương `student_text`.
5. Tạo character n-gram từ 3 đến 5.
6. Tính TF-IDF bằng vocabulary và IDF đã lưu.
7. L2 normalize text vector.
8. Trích xuất 20 E2 features từ raw URL.
9. Ghép text vector và E2 features.
10. Chạy LightGBM inference.
11. Tính sigmoid và so sánh threshold.

Cấu hình text vectorization:

- `ngram_range`: 3–5.
- `lowercase`: false.
- `sublinear_tf`: true.
- `norm`: L2.
- TF: `1 + ln(count)`.
- IDF: dùng đúng giá trị trong `features.json`.
- Character n-gram tính theo Unicode code points, không phải UTF-16 code units.

Dart cần xử lý Unicode tương đương Python, tránh dùng UTF-16 code-unit indexing nếu gây sai khác.

Canonicalization cần khớp Python reference, đặc biệt với:

- Scheme, userinfo và fragment.
- Hostname IDNA và lowercase.
- Path và query.
- Chữ hoa/thường.
- Percent-encoded characters.

Không tự ý thay đổi quy tắc canonicalization để làm cho kết quả có vẻ khớp.

### 3.4. Thứ tự 20 E2 features

Phải giữ nguyên thứ tự sau:

| Index | Feature |
|---:|---|
| 0 | `url_len` |
| 1 | `dom_len` |
| 2 | `is_ip` |
| 3 | `subdom_cnt` |
| 4 | `letter_cnt` |
| 5 | `digit_cnt` |
| 6 | `dot_cnt` |
| 7 | `dash_cnt` |
| 8 | `under_cnt` |
| 9 | `slash_cnt` |
| 10 | `entropy` |
| 11 | `path_len` |
| 12 | `brand_in_domain` |
| 13 | `brand_in_subdomain` |
| 14 | `brand_in_path` |
| 15 | `brand_domain_mismatch` |
| 16 | `brand_typo_score` |
| 17 | `susp_token_cnt` |
| 18 | `idna_flag` |
| 19 | `homoglyph_brand_hit` |

Có thể tái sử dụng `E2Extractor` hiện có trong `phishguard_features` nếu kiểm thử xác nhận cả 20 giá trị khớp Python reference.

Không sửa E2 feature order hoặc contract đã đóng băng để phù hợp với Student.

---

## 4. Quy trình kiểm thử Student

Thực hiện theo đúng thứ tự. Chỉ chuyển sang bước tiếp theo khi bước trước đã có kết quả kiểm tra.

### Bước 1 — Kiểm tra model loader

Viết tests cho Student model loader.

Các trường hợp cần kiểm tra:

- Manifest hợp lệ.
- Thiếu manifest.
- Thiếu model JSON.
- Thiếu features hoặc runtime assets.
- JSON không hợp lệ.
- SHA-256 mismatch.
- File size mismatch.
- Sai model schema hoặc feature schema.
- Sai threshold hoặc selected mode.
- Vocabulary và IDF không cùng kích thước.
- Feature order không đúng.
- Tree count không đúng.
- Tree node hoặc feature index không hợp lệ.
- Model initialization thất bại.

Kết quả mong muốn:

- Model hợp lệ được nạp thành công.
- Artifact không hợp lệ phải bị từ chối.
- Có lỗi rõ ràng để xác định nguyên nhân.
- Không fallback sang benign khi model không thể load.

### Bước 2 — Kiểm tra feature parity Python–Dart

Dùng cùng URL đầu vào để đối chiếu từng bước:

1. URL validation.
2. Canonical URL/text.
3. Character n-gram.
4. TF-IDF vector.
5. E2 feature vector.
6. Combined feature vector.

Các trường hợp cần chú ý:

- Unicode và IDNA hostname.
- URL có IP address.
- URL có port.
- Subdomain và public suffix.
- Path/query có chữ hoa và chữ thường.
- Percent-encoded characters.
- Brand typo và homoglyph.
- URL có ký tự hoặc cấu trúc bất thường.

Không chỉ so sánh final label. Cần kiểm tra intermediate features để xác định sai khác xuất hiện ở bước nào.

**Điều kiện đạt:** Feature vector của Dart khớp Python reference trong tolerance đã thống nhất.

### Bước 3 — Kiểm tra prediction parity Python–Dart

Dùng Student Python reference fixtures để đối chiếu kết quả inference.

Các trường cần so sánh:

- Raw score.
- Label.
- Class ID.
- Threshold.
- Model mode/version.
- Decision rule.

Yêu cầu:

- Mục tiêu sai khác score không vượt quá `1e-6`.
- Label và class ID phải khớp.
- Threshold và decision rule phải đúng.
- Có trường hợp score gần threshold để phát hiện lỗi có thể làm thay đổi label.

Nếu bộ reference có 52 trường hợp hợp lệ và 6 trường hợp reject, cần báo cáo riêng:

- Số trường hợp hợp lệ khớp.
- Số trường hợp bị reject đúng.
- Số trường hợp sai score/label.
- Các trường hợp chưa xử lý được.

Không lấy kết quả Teacher 41/41 hoặc E2 128/128 làm kết quả Student parity.

**Điều kiện đạt:** Student Dart adapter khớp Python reference trên bộ fixture tương ứng.

### Bước 4 — Chạy Dart/Flutter tests

Sau khi có Student adapter và model loader, chạy kiểm thử từ đúng package/app directory.

Ví dụ:

```bash
cd mobile/packages/phishguard_features
dart test
```

Với Flutter app:

```bash
cd mobile/app
flutter analyze
flutter test
```

Lưu lại toàn bộ kết quả.

Các test mới cần có tối thiểu:

- Student vectorization.
- Student tree evaluator.
- Student model loader.
- Student feature parity.
- Student prediction parity.
- Input validation.
- Error handling.

Lưu ý: Đây là kiểm thử laptop/Dart/Flutter environment, chưa phải Android runtime parity.

### Bước 5 — Build và chạy Android Emulator

Khởi chạy Emulator trong Android Studio.

Từ thư mục `mobile/app`, kiểm tra thiết bị:

```bash
flutter devices
```

Chạy ứng dụng trên Emulator:

```bash
flutter run -d <emulator_device_id>
```

Nếu cần build APK:

```bash
flutter build apk --release
```

Thay `<emulator_device_id>` bằng device ID thực tế hiển thị từ `flutter devices`.

Kiểm tra:

- APK build thành công.
- Ứng dụng cài đặt và khởi chạy.
- Student assets được đọc đúng.
- Model load thành công.
- Student inference chạy trên Android runtime.
- UI hiển thị đúng trạng thái và kết quả.

### Bước 6 — Android runtime parity

Đây là bước bắt buộc để xác nhận Student chạy đúng trong Android runtime.

Thực hiện:

1. Dùng cùng bộ fixture Python reference.
2. Chạy inference trực tiếp trên Android Emulator.
3. Thu score, label, class ID và threshold.
4. Đối chiếu với Python reference.
5. Ghi nhận số case pass/fail và sai khác lớn nhất.

Không dùng kết quả Dart package tests để tuyên bố Android runtime parity đã đạt.

**Điều kiện đạt:** Android runtime prediction khớp Python reference theo tolerance và decision contract đã thống nhất.

### Bước 7 — Offline smoke test

Trên Android Emulator:

1. Khởi chạy ứng dụng và xác nhận model đã load.
2. Tắt kết nối mạng hoặc bật Airplane Mode trên Emulator.
3. Đóng/mở lại ứng dụng để kiểm tra khả năng hoạt động sau khi khởi động lại.
4. Nhập URL kiểm thử.
5. Xác nhận Student vẫn thực hiện inference.
6. Xác nhận không gọi API hoặc phụ thuộc server.
7. Ghi lại kết quả và lỗi nếu có.

**Điều kiện đạt:** Student inference vẫn chạy khi Emulator không có Internet.

Offline smoke test và prediction parity là hai loại bằng chứng riêng, cần báo cáo riêng.

### Bước 8 — Kiểm thử lỗi

| Tình huống | Kết quả mong muốn |
|---|---|
| URL không hợp lệ | Báo lỗi input |
| Port không hợp lệ | Reject, không tạo prediction |
| Thiếu model asset | Báo lỗi load model |
| Manifest không hợp lệ | Reject |
| SHA-256 mismatch | Reject |
| Feature contract mismatch | Reject |
| Tree JSON không hợp lệ | Báo lỗi model/inference |
| Model initialization thất bại | Báo lỗi rõ ràng |
| E2 extraction thất bại | Không trả về benign mặc định |

Không chuyển lỗi validation, loading hoặc inference thành kết quả benign.

---

## 5. Performance testing

Chỉ thực hiện benchmark sau khi feature và prediction parity đạt.

Các chỉ số cần đo:

| Chỉ số | Nội dung |
|---|---|
| Cold-start | Thời gian từ lúc khởi chạy đến khi Student sẵn sàng |
| Model loading | Thời gian đọc và khởi tạo model/assets |
| p50 inference | Median inference latency |
| p95 inference | 95th percentile inference latency |
| RAM | Mức sử dụng RAM khi load và inference |
| APK size | Kích thước APK build |
| Student assets size | Tổng kích thước Student assets được đóng gói |

Nguyên tắc đo:

- Ghi rõ Emulator hay thiết bị thật.
- Ghi Android version, ABI, Flutter/Dart version.
- Dùng cùng bộ URL và số lần lặp khi so sánh.
- Tách cold-start khỏi inference latency.
- Không lấy thời gian Dart VM trên laptop thay cho Android runtime benchmark.
- Không ghi số liệu ước lượng như kết quả đo thực tế.

Nếu chưa có điện thoại Android thật, ghi rõ benchmark được thực hiện trên Emulator.

---

## 6. Báo cáo kết quả kiểm thử

Sau khi hoàn thành, cập nhật báo cáo trong thư mục `reports/`.

Báo cáo cần có:

1. Branch và commit đã kiểm thử.
2. Student model mode và artifacts.
3. Môi trường kiểm thử: laptop, Emulator hay thiết bị thật.
4. Các lệnh đã chạy.
5. Tổng số test passed/failed.
6. Python–Dart feature parity.
7. Python–Dart prediction parity.
8. Android runtime parity.
9. Offline smoke test.
10. Error handling.
11. Cold-start, p50/p95, RAM, APK và assets size.
12. Các lỗi và giới hạn còn lại.

### Phân biệt các kết quả parity

Khi báo cáo, phải tách riêng:

| Loại kiểm thử | Xác minh điều gì? |
|---|---|
| E2 extractor parity | E2 feature extraction |
| Teacher v2 parity | Teacher inference |
| Student feature parity | Student feature vector |
| Student prediction parity | Student model output |
| Student Android runtime parity | Student inference trực tiếp trên Android |

Các kết quả đã có từ PR #21 và PR #33 chỉ là bối cảnh tham khảo cho E2/Teacher. Chúng không thay thế kiểm thử Student.

---

## 7. Definition of Done

### Student implementation và parity

- [ ] Student model loader đọc đúng manifest và artifacts.
- [ ] SHA-256 và file size được kiểm tra.
- [ ] Feature contract và feature order được xác minh.
- [ ] Python–Dart feature parity đạt.
- [ ] Python–Dart prediction parity đạt.
- [ ] Input validation và model loading errors được kiểm thử.
- [ ] Không có lỗi fallback thành benign khi inference thất bại.

### Android runtime

- [ ] Flutter Android build thành công.
- [ ] APK cài đặt và khởi chạy trên Emulator.
- [ ] Student assets được nạp trên Android.
- [ ] Student inference chạy trực tiếp trên Android runtime.
- [ ] Android runtime parity được đối chiếu với Python reference.
- [ ] Offline smoke test đạt.
- [ ] Error handling trên Android được kiểm tra.

### Performance và báo cáo

- [ ] Có cold-start measurement.
- [ ] Có p50/p95 inference latency.
- [ ] Có RAM measurement.
- [ ] Có APK size và Student assets size.
- [ ] Ghi rõ môi trường đo.
- [ ] Có báo cáo kết quả và giới hạn còn lại.

### Kiến trúc

- [ ] Teacher v2 vẫn hoạt động bình thường.
- [ ] Student chưa được tự động thay Teacher làm engine mặc định.
- [ ] Không thay đổi Teacher model, threshold hoặc E2 contract ngoài phạm vi được duyệt.

Nếu chưa có điện thoại thật:

- [ ] Ghi rõ physical-device validation chưa thực hiện.
- [ ] Không tuyên bố đã kiểm thử trên thiết bị Android thật.

---

## 8. Thứ tự ưu tiên thực hiện

1. Kiểm tra Student artifacts và Python reference.
2. Viết Student Dart model loader và adapter.
3. Đạt Python–Dart feature parity.
4. Đạt Python–Dart prediction parity.
5. Chạy Dart/Flutter tests.
6. Build và chạy trên Android Emulator.
7. Đạt Android runtime parity.
8. Kiểm tra offline và error handling.
9. Đo performance.
10. Cập nhật báo cáo và bàn giao.

**Kết luận:** Không cần chờ điện thoại Android thật mới bắt đầu. Laptop và Android Emulator đủ để thực hiện phần lớn công việc tích hợp, kiểm thử và xác minh Student. Phần kiểm thử trên thiết bị thật sẽ được ghi nhận riêng khi có thiết bị.