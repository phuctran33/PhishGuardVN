# Ma trận kiểm thử tuần 7 — Khiêm

Ma trận này bổ sung phạm vi tuần 7; không thay thế hay lặp lại bộ QA tuần 6 đã hoàn tất. URL tổng hợp ưu tiên `example.com`; các tên thương hiệu dùng reference đã phát hành. Mọi URL chỉ được xử lý dưới dạng chuỗi, không mở URL đích.

## Fixtures dùng lại

- `tests/conftest.py::valid_url_cases`: URL có/không scheme, Unicode, IPv4 và IPv6.
- `tests/conftest.py::invalid_url_cases`: chuỗi rỗng, port sai, IPv6 sai định dạng và hostname có khoảng trắng.
- `tests/conftest.py::mock_model`, `mock_bundle`, `mock_prediction_result`: kiểm tra luồng mock API, không thay thế kiểm tra Teacher thật.
- `tests/test_brand_features.py`: các URL Vietcombank giả mạo, subdomain gây nhầm, typo, homoglyph và URL có tên thương hiệu trong path; kiểm tra feature và rule giải thích hiện hành.
- `tests/README.md`: hướng dẫn cài môi trường, chạy pytest, Teacher/API gate, backend thật, Flutter và xem kết quả CI tuần 6.
- Bàn giao Web `701b8f5`: `apps/web/test/fixtures/` đã có QR PNG/JPEG/WebP, QR không phải URL, sai scheme, ảnh không QR/hỏng và header ảnh quá giới hạn. Dùng trực tiếp fixtures này trong checkout bàn giao; kết quả QA thực tế tại `reports/week7_qa.md`.

## K7.1 — QR

| ID | Ca kiểm thử | Điều cần xác nhận |
| --- | --- | --- |
| QR-01 | Ảnh QR chứa `https://example.com/login?src=qr-test` | Giải mã URL; chỉ gửi URL đó tới `/predict` sau thao tác xác nhận theo luồng sản phẩm; hiển thị đúng response backend. |
| QR-02 | Ảnh QR chứa URL sai như `http://example.com:99999/` | Báo lỗi URL theo contract; không gọi nhầm sang kết quả dự đoán thành công. |
| QR-03 | QR chứa chuỗi thường `not-a-url` | Từ chối như dữ liệu không phải URL; không gọi `/predict`. |
| QR-04 | Ảnh không có QR, ảnh rỗng và bytes ảnh hỏng | Hiển thị lỗi đọc/giải mã có thể hiểu được; giao diện không crash và không gửi request dự đoán. |
| QR-05 | Backend trả lỗi validation, 503 hoặc mất kết nối sau khi giải mã | Hiển thị lỗi tương ứng; không biến lỗi thành nhãn hoặc điểm giả. |
| QR-06 | Backend phản hồi chậm rồi thành công hoặc timeout | Loading kết thúc đúng trạng thái; retry không gửi lặp ngoài ý muốn và không yêu cầu tải lại trang. |

Đã kiểm QR-01–QR-06 trên snapshot Hưng `5f112fc`: kết hợp 48 Flutter tests với 20 browser checks thật. Ảnh rỗng/giới hạn bytes và timeout được kiểm có kiểm soát trong unit tests; browser kiểm decode ảnh thật, xác nhận, lỗi ảnh, mất kết nối/restart và model degraded. Không gọi coverage unit có HTTP mock là E2E thật. Ca focus sau QR lỗi đã sửa và giữ làm regression riêng (1/1 pass).

## K7.2 — Brand Detector / X-Ray

| ID | Ca kiểm thử | Điều cần xác nhận |
| --- | --- | --- |
| BX-01 | Domain chính thức có trong reference | Nhận diện domain/brand theo reference; không gắn cờ mạo danh chỉ vì URL có path thông thường. |
| BX-02 | Domain giả mạo dùng tên brand trong hostname, ví dụ `https://vietcombank-login.top/verify` | X-Ray tách đúng hostname/registrable domain và hiển thị rule gây cảnh báo. |
| BX-03 | Brand ở subdomain chính thức và brand bị nối vào domain khác, ví dụ `https://login.vietcombank.com.vn/` và `https://vietcombank.com.vn.xacminh-id.xyz/` | Phân biệt host thực với chuỗi con; không xem việc có tên brand ở bất kỳ vị trí nào là domain chính thức. |
| BX-04 | Alias đã khai báo và alias gần giống nhưng không có trong reference | Chỉ áp dụng alias theo reference; hiển thị rule/nguồn giải thích được. |
| BX-05 | Unicode hostname và biểu diễn IDNA/punycode tương ứng | Parser/X-Ray nhất quán về hostname chuẩn hóa; không làm mất dấu hiệu IDNA/homoglyph hiện có. |
| BX-06 | IPv4, IPv6, URL lỗi và URL có port sai | Xử lý đúng loại host hoặc trả lỗi validation theo contract; không crash. |
| BX-07 | Cùng một URL qua Brand Detector và ML prediction | Rule-based signals được trình bày riêng; không tự sửa label, score, threshold hay metadata của Teacher. |
| BX-08 | Sau khi chạy các ca trên | Hash và nội dung reference E2 đã phát hành không đổi. |

Đã kiểm BX-01–BX-08 trên cùng snapshot bằng API upstream, inspection QA và regression hiện có. BX-04 dùng lại test alias theo whole-token và các ca official-domain/false-positive/reference trong `test_brand_features.py`, không viết lại brand engine hoặc thay reference để làm test pass. Bằng chứng và giới hạn tại [`week7_qa.md`](week7_qa.md#chốt-phạm-vi-bàn-giao-hưng-và-phúc).

## K7.3 — Android Teacher

| ID | Ca kiểm thử | Điều cần xác nhận |
| --- | --- | --- |
| AT-01 | Python và Dart chạy cùng bộ URL fixture | So sánh feature/score theo tolerance đã thống nhất và label theo cùng threshold; ghi từng lệch nếu có. |
| AT-02 | Score nhỏ hơn, bằng và lớn hơn threshold đã khóa | Label tuân theo đúng quy tắc phát hành `score >= threshold`; không mặc định score là phần trăm đã hiệu chuẩn. |
| AT-03 | Đọc metadata và model assets trên Android | Version, SHA-256, feature/preprocessing protocol và threshold khớp release lock. |
| AT-04 | Chặn mạng hoàn toàn rồi predict URL fixture | Teacher vẫn suy luận offline; ghi nhận request mạng nếu có và xác định nguồn của request. |
| AT-05 | Thiếu asset, asset hỏng, sai hash hoặc metadata không tương thích | Báo lỗi load rõ ràng; không trả prediction giả hoặc dùng model khác âm thầm. |
| AT-06 | URL hợp lệ, URL Unicode/IDNA, IP, URL lỗi và chuỗi rỗng | Python–Dart xử lý cùng contract; ghi rõ trường hợp hai phía khác nhau. |

## K7.4 — Student

| ID | Ca kiểm thử | Điều cần xác nhận |
| --- | --- | --- |
| ST-01 | Student artifact và cấu hình inference | Ghi version, SHA-256, preprocessing/feature protocol và runtime yêu cầu; đối chiếu với thông tin bàn giao. |
| ST-02 | Python reference chạy trên bộ URL fixture chung | Lưu output dự đoán và score làm đầu vào đối chiếu; không dùng dữ liệu Official Test để chọn/chỉnh model. |
| ST-03 | Python–Dart trên cùng input khi có Android adapter | So sánh score theo tolerance đã thống nhất, label theo operating point được bàn giao và kiểm tra edge cases. |
| ST-04 | Artifact/config sai version, thiếu hoặc hash không khớp | Ghi nhận lỗi cụ thể; không nhận nhầm kết quả Teacher thành kết quả Student. |

Bàn giao Student `1cad94c88195ebea6e4737bbfc863cbe4b2ff384`: ST-01/ST-02 và phần Python của ST-04 đã kiểm bằng `tests/week7/student_qa.py` (**43 passed**), cùng 3 test LightGBM và 29 test Student cũ. Đã kiểm 52 fixture hợp lệ/6 lỗi ở từng mode, native–JSON parity, threshold, assets, portable offline inference và lineage CV targets. ST-03 chưa chạy do chưa nhận Android Student adapter/build; không nhận Python parity thay cho Android. Kết quả chi tiết tại [`week7_qa.md`](week7_qa.md#k74--kiểm-student-lightgbm-ngày-18112026) và [`student_verification.json`](tables/week7/student_verification.json).

## K7.5 — CI, regression và smoke test

| ID | Ca kiểm thử | Điều cần xác nhận |
| --- | --- | --- |
| CI-01 | Dart package | CI chạy `dart test` trên package có test Dart. |
| CI-02 | Flutter app | CI chạy `flutter analyze` và `flutter test` trong thư mục app. |
| CI-03 | Python API/Teacher regression | Chạy lại suite tuần 6 và Teacher API gate hiện có; giữ nguyên điều kiện gate và không đổi skip thành pass. |
| CI-04 | Web → FastAPI → Teacher thật | Dùng backend và release Teacher thật; thử URL hợp lệ, URL sai và backend mất kết nối. Không dùng HTTP mock làm bằng chứng E2E. |
| CI-05 | Android Teacher offline | Tắt mạng, chạy inference thật trên Android build và ghi model/version cùng kết quả. |
| CI-06 | Báo cáo nghiệm thu | Ghi revision, OS/runtime, lệnh, artifact/hash, số pass/fail/skip và expected/actual cho lỗi; chỉ ghi pass khi ca đã chạy thực tế. |

Cập nhật `5f112fc` (18/11): CI-04 đạt **20/20** trên Chromium Windows/Teacher thật; ca focus riêng **1/1**. CI-01/CI-02 đã chạy tại máy (294 Dart tests, 48 Web tests, 3 app widget tests; analyze sạch) và có workflow Ubuntu/Windows; Actions mới chờ người dùng commit/push. CI-03 dùng lại gate Teacher 15 tests, API 73 tests, inspection QA 25 tests và full source 612 passed/3 skipped/1 deselected. CI-05 chưa thực hiện Android offline/device, CI-06 đang tích lũy bằng chứng, chưa nhận nghiệm thu cuối. Chi tiết và các giới hạn xem [`week7_qa.md`](week7_qa.md#k75--regression-và-kiểm-lại-sửa-focus-ngày-18112026).

## Quy ước ghi bằng chứng

Mỗi lần chạy ghi: mã ca, revision, thiết bị/OS/runtime, lệnh, model/version/hash, kết quả mong đợi, kết quả thực tế và pass/fail/skip. Không ghi raw URL riêng tư, token hay đường dẫn máy cá nhân. Các ảnh QR dùng payload tổng hợp trong bảng K7.1; không dùng QR trỏ tới website thật.
