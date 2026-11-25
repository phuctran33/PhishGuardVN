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

## Week 7 — QR ảnh, Brand Detector và URL X-Ray (#30)

Tiếp tục giao diện và design system trên; không thêm dashboard. QR dùng
[file_selector](https://pub.dev/packages/file_selector) 1.1.0 để chọn ảnh,
[image](https://pub.dev/packages/image) 4.13.1 đọc pixel và
[zxing2](https://pub.dev/packages/zxing2) 0.2.4 giải QR thực bằng Dart.
PNG/JPEG/WebP, tối đa 8 MiB và 4 × 1024² pixel; hỗ trợ **một QR/ảnh**,
chưa hỗ trợ nhiều QR/camera. Ảnh được decode local, không gửi lên backend.
QR phải chứa URL web; xác nhận người dùng mới gửi URL đến `/predict`.
Không nhấn/open website đích. File picker cancel không gửi request.

Bốn luồng demo (backend Teacher và Web release chạy theo hướng dẫn trên):

1. Nhập `example.com` → **Kiểm tra URL**: nhãn/score/model/threshold từ API.
2. **Chọn ảnh QR** → chọn `test/fixtures/qr_url.png` → xem URL đầy đủ →
   **Xác nhận và phân tích**: chỉ lúc này mới POST. Dùng `broken.png`, `no_qr.png`,
   `qr_text.png` và `qr_bad_scheme.png` để kiểm tra lỗi và chọn ảnh khác.
3. Nhập `https://vietcombank.com.vn/` → **Brand Detector & URL X-Ray**:
   xem đối chiếu reference; thử `https://vietcombank.com.vn.example.com/login`
   để thấy thương hiệu trong subdomain và domain đăng ký thực tế.
4. Cùng panel X-Ray: thử `https://bücher.de/Path`, `http://127.0.0.1/login`,
   `https://example.com/vietcombank?login=1`; heuristic tách rõ khỏi dự đoán ML.

Đổi input sẽ hủy hiển thị kết quả cũ và bỏ response đã lỗi thời (HTTP có thể
vẫn hoàn tất); request cùng loại không gửi trùng trong khi chờ. Giữ input khi
lỗi; có retry cho prediction, inspection và ảnh QR. Timeout API 10 giây.
Dừng backend thật rồi thử lại; restart backend/retry phải phục hồi không reload.
Reference inspection độc lập model: model unavailable vẫn có thể kiểm quy tắc.

Kiểm thử: `flutter analyze`, `flutter test`,
`flutter build web --release --dart-define=API_BASE_URL=http://127.0.0.1:8000`.
Ảnh fixture được tạo bằng Python qrcode/Pillow, đi qua decoder thật trong tests;
HTTP fixtures chỉ dành unit/widget tests. Bằng chứng mới và bàn giao QA #31:
[week7_web_verification.md](../../reports/week7_web_verification.md).


## Tuần 8–9 — danh mục mở rộng và ca tương tự (#38)

- Nhập URL hoặc chọn **Dán URL**, sau đó nhấn **Enter** hoặc **Kiểm tra URL**.
  Nút **Xóa URL** trả con trỏ về ô nhập và xóa kết quả cũ. Khi trình duyệt
  chặn quyền đọc bộ nhớ tạm, có thể dán trực tiếp vào ô nhập.
- **Chọn ảnh QR** hiển thị bản xem trước để xác nhận riêng. **Chỉnh URL**
  đưa con trỏ về ô nhập khi URL sai. Dùng **Thử lại** khi đã khôi phục kết nối.
- Nhập `https://napas.com.vn/` rồi chọn **Brand Detector & URL X-Ray** để thấy
  domain đăng ký, tên NAPAS, phiên bản/số thương hiệu và SHA-256 danh mục.
  `https://napas.com.vn/vietcombank` cho thấy ca có tên thương hiệu khác ở path.
  Dải trạng thái báo rõ nếu backend đang dùng reference gốc.
- **Tìm ca phishing tương tự** gọi endpoint riêng khi người dùng chọn. Nếu endpoint
  chưa có, giao diện báo chưa sẵn sàng và có nút thử lại ngay trên panel.
  Teacher prediction và kết quả inspection không phụ thuộc tra cứu lịch sử.
  Contract và fixture #36 đang ở trạng thái đề xuất.
- Các ca lịch sử khi có response hợp lệ hiển thị dưới dạng chữ, tối đa 5,
  kèm nguồn ghi nhận, cosine và phần giống. Fixture có nhãn dành cho kiểm thử.

[Bản ghi chạy thật, ảnh và bàn giao Hy/Khiêm](../../reports/week8_9_hung_verification.md) · [API contract](../../docs/api_contract.md)
