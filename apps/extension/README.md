# PhishGuardVN cho Chrome

Extension Manifest V3 kiểm tra link người dùng chọn qua cùng API Teacher với Web. Cần Chrome hoặc Chromium và backend theo [hướng dẫn FastAPI](../../docs/backend.md).

## Cài và demo

1. Chạy FastAPI theo chế độ `teacher` với CPython 3.11. Mở `http://127.0.0.1:8000/health` và xác nhận `model_ready: true` cùng `model: teacher-stacking-v2`.
2. Mở `chrome://extensions`, bật **Developer mode**, chọn **Load unpacked** rồi chọn đúng thư mục `apps/extension` trong checkout. Sau khi đổi source, dùng **Reload** ở trang này.
3. Mở một trang có hyperlink. Nhấn chuột phải vào link → **Kiểm tra bằng PhishGuardVN**. Cửa sổ, hostname, nhãn và phiên bản engine xuất hiện ngay trong Chrome. Score và threshold lấy từ `/predict`.
4. Mặc định backend là `http://127.0.0.1:8000`. Chọn **Cấu hình backend** trong cửa sổ kết quả hoặc **Extension options** trên trang Details. Lưu địa chỉ gốc `https://…` hoặc HTTP loopback `localhost`/`127.0.0.1`. Chrome có thể hỏi quyền truy cập riêng cho hostname mới. Nếu backend đang khởi động, chờ ready rồi chọn **Thử lại** trong cửa sổ đang mở.

Dùng ca an toàn khi demo. Ví dụ dùng một trang HTML cục bộ chứa link `https://www.vietcombank.com.vn/` và link tổng hợp `https://vietcombank-verify.example.net/login/secure?mode=demo`. Chọn menu trên link và đối chiếu với POST `/predict`. Các ca 422, offline, 503, timeout và retry có trong checklist và biên bản kiểm thử. [Kết quả và ca demo](../../reports/week8_9_hung_verification.md)

## Quyền và dữ liệu

- `contextMenus` đăng ký menu riêng cho hyperlink. `storage` chỉ lưu địa chỉ backend do người dùng chọn.
- Quyền mặc định là HTTP tới `127.0.0.1` theo match pattern của Chrome. Tùy chọn HTTPS và `localhost` xin quyền theo hostname khi người dùng lưu. Chrome cấp quyền hostname trên các cổng của scheme tương ứng. Đổi backend sẽ thu hồi quyền tùy chọn cũ.
- URL được chuyển một lần qua bộ nhớ cho cửa sổ kết quả. URL chỉ tồn tại trong bộ nhớ cửa sổ để người dùng thử lại. Payload chỉ gồm `{"url":"…"}` tới `POST /predict`. Fetch bỏ credential tự động, cache và redirect. Cửa sổ chỉ hiển thị hostname. Extension dùng extension pages và service worker, không có content script, quyền lịch sử hay telemetry.
- Thiết lập địa chỉ backend tin cậy. Một link có thể mang thông tin riêng tư trong path, query hoặc userinfo.
- Score Teacher chưa hiệu chuẩn nguy cơ thực tế. Nhãn benign có nghĩa là mô hình chưa phát hiện dấu hiệu phishing ở ngưỡng đang phục vụ.

```sh
node --test apps/extension/tests/*.test.mjs
```

Bộ test Node kiểm manifest, quyền, URL/config boundary, schema, status lỗi và timeout. Kiểm native context menu dùng Chrome for Testing và backend Teacher thật. [Chi tiết thực thi](../../reports/week8_9_hung_verification.md)
