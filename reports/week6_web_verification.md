# Week 6 — Flutter Web #19 → released stacking Teacher, 13/11/2026

PR #23 vẫn stacked trên backend PR #22; backend đã đồng bộ main `7d2d600` chứa upstream Teacher review `398ee2c` qua PR #27. Diff Web chỉ có apps/web, README và bằng chứng Web; không lặp code API hoặc bảng benchmark Phúc. Không thiết kế lại giao diện, đổi framework hoặc sửa pipeline Teacher.

## Luồng tích hợp hiện tại

Flutter Web release → FastAPI thật → `load_teacher(repo_root)` chính thức → **teacher-stacking-v2**. Runtime **CPython 3.11.17**, preprocessing **canonical-reference-v1**; artifact SHA256 **63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1**. Threshold đọc từ lock **0.6945740700635259**, rule **score >= threshold**, không hardcode threshold/path/SHA candidate trong code.

Parser hỗ trợ rule stacking và threshold hữu hạn có điều kiện, giữ numeric estimator.predict cũ. UI giữ nguyên label backend, hiển thị meta-LR score dạng số (không % an toàn/nguy cơ), ghi chưa hiệu chuẩn và rule/threshold backend. Nhãn benign không bảo đảm an toàn. Loading/chống gửi trùng/error/retry/responsive và thiết kế navy/cyan/red Glassmorphism Material 3 giữ nguyên.

## Kiểm thử thực tế

| Kiểm tra | Kết quả |
|---|---|
| Flutter 3.47.9 / Dart 3.13.7 analyze | **No issues found** |
| flutter test | **28 passed, 0 failed, 0 skipped** |
| Release Web build, --no-web-resources-cdn | **PASS**, fonts/CanvasKit phục vụ local |
| Chrome headless, API/model thật, không route mocks | **9/9 nhóm tình huống PASS**, 0 page errors |
| Responsive/reduced motion/Enter | 390×844, 320×844, 844×390 landscape, 768×1024, 1440×900: gọi Teacher thật và không document horizontal overflow |
| Python CLI–API (backend report) | 13/13 khớp score/label/threshold; max score delta 0.0, atol 1e-12 |

Fixtures unit/widget chỉ phục vụ validation/trạng thái: rule lạ, threshold thiếu/sai/NaN/inf, margin vs probability, score .6/threshold .7 nhưng label benign; không dùng fixtures để chụp ảnh hoặc nhận demo Teacher. Mobile là viewport emulation trên Chrome, không nhận đã kiểm điện thoại Android thật. Các checks accessibility có phạm vi cụ thể, không phải audit WCAG đầy đủ.

## Các tình huống Web → API → Teacher đã chạy

| Tình huống | Kết quả quan sát |
|---|---|
| HTTPS hợp lệ, score nằm giữa .5 và threshold | `https://example.com/Login?Q=A`: score **0.5760558654872865**, label **benign**, threshold chính xác từ lock; UI **0.576056**, không suy thành phishing ở .5 |
| Nhánh phishing thật | URL thuộc Validation, ID **024efd11-58b4-57c4-8d40-383a1034b19f**, split val đã kiểm; domain vô hiệu hóa **9944789[.]com**. Teacher trả phishing, UI cảnh báo đỏ và giữ score/rule. Không truy cập website hoặc thay nhãn dataset |
| Input rỗng | Lỗi tại form, không gửi POST |
| Thiếu scheme | `example.com`: Teacher trả benign, model/version/score đúng |
| Port sai | HTTP 422 invalid_port, error card và retry |
| Model unavailable | Dừng/restart API với release root rỗng riêng; HTTP 503/health degraded, UI báo chưa sẵn sàng; không sửa/xóa artifact chính thức hoặc fallback |
| Backend mất kết nối | Dừng thật process bằng SIGTERM; UI báo mất kết nối, không prediction giả |
| Restart/retry | Restart với root chứa lock/bundle chính thức, nút Thử lại trên cùng trang phục hồi Teacher, không reload |
| Desktop/mobile/tablet | Gửi bằng Enter, reduced motion, score/label thật; không horizontal overflow |

Mọi HTTP request do trang phát trong lượt kiểm chỉ đến **127.0.0.1**, gồm assets và API; không request tới URL input. JSON từng case, artifact/revision và screenshot/source hashes: [web_smoke.json](tables/week6/web_smoke.json), mục **current_teacher**. Revision nền khi build không phải commit publish sau kiểm thử; source hashes định danh đúng code đã chạy.

## Ảnh render Teacher thật

![Benign, score trên .5 nhưng dưới threshold](figures/week6_web/desktop.png)

![Teacher phishing trên URL Validation](figures/week6_web/phishing.png)

![Mobile sau khi tự cuộn tới kết quả](figures/week6_web/mobile.png)

![Release root thiếu artifact, 503 thật](figures/week6_web/unavailable.png)

![Backend dừng thật, lỗi và retry](figures/week6_web/offline.png)

Không có video được nhận là đã quay; đây là screenshot browser thật, không ảnh sinh/mockup. Không mở URL nguy hiểm.

## Lịch sử E1 và bảo toàn nghiên cứu

Bằng chứng **09/11/2026 dùng E1** `logistic_regression_balanced / lexical_12`, artifact SHA `6bd8324a56bba9f98615599419349947f461f77d6a9e11f578db22836dd6014c`, protocol `week5_e1_audit`, không phải stacking. Record giữ ở **legacy_e1_2026_11_09** trong JSON; bốn ảnh cũ chuyển nguyên bytes vào [legacy_e1_2026_11_09](figures/week6_web/legacy_e1_2026_11_09/). Không đổi tên output E1 thành Teacher. Design system UI UX Pro Max 2.15.0 và các tests/ảnh 09/11 thuộc mốc lịch sử riêng.

Không train/retrain/tune, đổi threshold/model bytes/lock/promotion, sửa raw data/labels/splits/folds, E1/E2/reference, notebook outputs hoặc kết quả benchmark của Phúc. Không chạy external hoặc Official Test cho tích hợp. Giữ guards runtime 3.11/source/reference của loader chính thức.

## Bàn giao #15/#19 và hậu kiểm #17

[API contract v1](../docs/api_contract.md), [backend CPython 3.11 và release lock](../docs/backend.md), [Flutter setup/build/smoke](../apps/web/README.md). API `http://127.0.0.1:8000`, Web `http://127.0.0.1:3000`, CORS đúng hai localhost origins. Checkout Git có artifact/lock chính thức, không phụ thuộc cache riêng của Hưng; không dùng máy thiếu artifact để nhận integration pass.

DoD #15 và luồng #19 đã có bằng chứng local Web → API → Teacher thật; chờ review PR, không tự merge/đóng issue. Không còn blocker thiếu Teacher #16 cho luồng Web. Khiêm #17 vẫn phụ trách QA/security/latency/clean-clone và final smoke trước nghiệm thu 15/11; không đánh dấu thay Khiêm. Không mở rộng KD/Student/Android/deployment.
