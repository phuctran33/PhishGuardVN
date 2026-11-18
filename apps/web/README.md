# PhishGuardVN — Flutter Web (#19)

Ứng dụng Web gửi URL tới API v1, không tự tính feature hoặc mở website đích. Backend/contract thuộc PR #22 / issue #15. Ứng dụng Web nằm riêng `apps/web/`, không thay code Android/parity của Hy trong `mobile/`.

## Thiết kế

Design system tạo bằng **UI UX Pro Max 2.15.0**, đã đọc và chạy scripts thật: [MASTER.md](design-system/phishguardvn/MASTER.md). Dark navy + cyan/teal, Glassmorphism tiết chế, bố cục Minimalism / Swiss, Material 3; cảnh báo phishing đỏ kèm icon và chữ. Font Roboto bundle local hỗ trợ tiếng Việt. Một card kính mờ, không dashboard hoặc telemetry giả. Input và nút có focus/keyboard semantics; trạng thái wrap ở màn hình hẹp, hỗ trợ tăng cỡ chữ và reduced motion. API contract/inference không phụ thuộc skill.

## Chạy từ máy mới

Đã kiểm chứng bằng **Flutter 3.47.9 / Dart 3.13.7** (stable), Chrome; xem [Flutter Web setup](https://docs.flutter.dev/platform-integration/web/setup). Chỉ cần Flutter/Web, không cần Android Studio/Xcode để chạy target Web. Python backend xem [hướng dẫn](../../docs/backend.md) và [API contract](../../docs/api_contract.md).

1. Từ repository root: tạo venv bằng **CPython 3.11**, cài `python -m pip install -r requirements-teacher.txt -e '.[api,test]'`.
2. Dùng `PHISHGUARD_BUNDLE_FORMAT=teacher`, `PHISHGUARD_TEACHER_ROOT` là checkout chứa release lock/artifact chính thức theo `docs/backend.md`; bỏ override MODEL_BUNDLE/MODEL_NAME cũ; đặt CORS `http://localhost:3000,http://127.0.0.1:3000` và chạy API port 8000.
3. Kiểm tra `/health`: model_ready phải true để có inference thật. Checkout mới đã có bundle chính thức qua Git; thiếu/sai lock/bundle/runtime vẫn degraded/503, không fallback E1.
4. Mở terminal khác:

```sh
cd apps/web
flutter pub get
flutter run -d chrome --web-hostname 127.0.0.1 --web-port 3000 --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

`API_BASE_URL` là cấu hình compile-time, không chứa secret; thay giá trị cần chạy/build lại. Nếu đổi hostname/port Web thì đổi CORS allowlist backend tương ứng. `localhost` và `127.0.0.1` là hai origin khác nhau. Dùng URL `http://127.0.0.1:3000` cho cùng thiết lập demo.

Bản release local:

```sh
flutter build web --release --no-web-resources-cdn --dart-define=API_BASE_URL=http://127.0.0.1:8000
python -m http.server 3000 --bind 127.0.0.1 --directory build/web
```

Frontend không tự hạ cấp HTTPS sang HTTP. Demo trên host khác phải dùng base URL/CORS phù hợp, không cần production deployment. Font Roboto và license được bundle local; không có Google Fonts runtime package, không lưu lịch sử URL hoặc thông tin form vào local storage.

## Hành vi và score

- UI responsive desktop/mobile, có loading/error/retry. Nút bị khóa trong khi request đang chạy; input được giữ khi lỗi để sửa/thử lại mà không reload trang.
- URL rỗng hoặc quá 4096 Unicode code points được báo ở form. Các kiểm tra URL/Unicode/IP/port còn lại do parser backend quyết định; thiếu scheme được gửi nguyên cho API. Frontend không duplicate extractor.
- Nhãn hiển thị từ backend. Stacking hiển thị **meta-LR score chưa hiệu chuẩn** dạng số và threshold/rule backend, không suy nhãn ở .5; numeric probability cũ hiển thị phần trăm **predict_proba chưa hiệu chuẩn**, không gọi là xác suất URL thực sự độc hại. SVM margin hiển thị số, không có `%` và ghi không phải xác suất.
- Benign không đồng nghĩa an toàn. Không nhập URL chứa credential/token thật vào demo.
- Timeout 10 giây, backend offline, lỗi API/model thiếu hoặc response lệch contract được báo rõ; có nút Thử lại. Không fallback prediction giả.

## Model hiện tại và Teacher #16

Teacher hiện tại là **teacher-stacking-v2**, thông qua loader chính thức và `configs/teacher_lock.json` trên CPython 3.11. Canonical char TF-IDF/SVM + E2 HistGB → meta LR; backend đọc threshold/protocol/hash từ lock, frontend giữ nguyên label. Không đổi tên artifact vì còn chữ candidate, không chỉnh promotion, không train/tune/benchmark. [Release guide](../../docs/teacher_v2_release.md).

Bằng chứng 09/11 dùng E1 `logistic_regression_balanced / lexical_12` giữ riêng trong smoke records lịch sử. Bằng chứng Teacher mới ở báo cáo/JSON hiện tại; không đổi tên ảnh E1 thành Teacher.

## Kiểm thử / hậu kiểm cho Khiêm (#17)

```sh
flutter analyze
flutter test
```

Unit/widget tests dùng HTTP fixtures synthetic chỉ để kiểm tra trạng thái UI/parser response, không dùng làm demo nghiệm thu. Bằng chứng browser thật xem [week6_web_verification.md](../../reports/week6_web_verification.md); các screenshots không phải mockup.

Các bước smoke tối thiểu (API + Web thực):

1. `https://example.com`: thấy nhãn, model và score từ backend thật.
2. Xóa input rồi bấm Kiểm tra: lỗi tại form, không gửi POST.
3. `example.com`: backend chấp nhận thiếu scheme và trả kết quả.
4. `http://example.com:99999`: lỗi URL, vẫn sửa được input.
5. Dừng backend nhưng giữ Web mở, gửi lại: lỗi mất kết nối. Khởi động backend lại và bấm Thử lại: kết quả phục hồi không reload.
6. Tùy chọn bỏ cấu hình model/restart: UI báo máy chủ chưa sẵn sàng, không sinh label giả.

Hưng bàn giao Web/config/ảnh demo ở PR riêng; Khiêm vẫn phụ trách QA/security/CI đầy đủ, clean clone và final E2E smoke hậu kiểm trước nghiệm thu 15/11. Trạng thái tích hợp Teacher và các giới hạn kiểm chứng được ghi theo lượt chạy thực tế trong báo cáo; không nhận fixtures unit là demo Teacher. Không có video được nhận là đã quay; có screenshot thật và các bước ở trên để tự quay lại.
