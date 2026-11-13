# Báo cáo QA API — Issue #17

## Phiên bản được kiểm tra

- QA: nhánh `test/api-contract-qa`, HEAD `cef4aea917711188931c0849f5caee9911c70ff4`, có thay đổi chưa commit.
- Backend PR #22: `7dfeec5f96f106f3544163466e2cf312494eb41f`.
- Web PR #23: `a2bb0dcedb7d12777774462a5fdea680aca2ff7e`.
- Main bàn giao: `7d2d60091c971dd3081b0b71fbf35b4cdd80c165`; Teacher đã phát hành qua `398ee2ce9e587644ebe21b529fba485536a9aac1`.
- Teacher hiện tại: `teacher-stacking-v2`, preprocessing `canonical-reference-v1`, `promoted=true`. File bundle giữ tên lịch sử `models/teacher_v2_candidate.joblib`.
- SHA256 bundle: `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`; ngưỡng đọc từ release lock: `0.6945740700635259`.
- Windows build 26200, CPython **3.11.14**; tất cả runtime libraries khớp `requirements-teacher.txt`. `pip check` đạt. Flutter 3.47.9 / Dart 3.13.7; Chrome headless bằng profile tạm.

## Kết quả kiểm chứng độc lập

| Phần kiểm tra | Kết quả thực tế |
| --- | --- |
| Full suite QA, bật `--teacher-api` | **490 passed, 2 skipped in 56.46s**; một warning escape sequence có sẵn trong `week5_reporting.py`. |
| QA Teacher/parity/security và benchmark tập trung | **53 passed in 20.81s**; gồm 32 bài Teacher/API và 21 bài benchmark. |
| API/Teacher tests nguyên bản của Hưng | **47 passed, 1 failed in 7.33s**; lỗi bootstrap test trên Windows, chi tiết bên dưới. |
| Full suite PR #22, có extras teacher/research | **552 passed, 2 skipped, 1 failed, 1 deselected in 65.62s**. Loại đúng bài `test_real_external_bundle_matches_saved_scores`; không chạy external scoring cho tác vụ QA. |
| Đề xuất sửa test Windows, chỉ trên bản sao tạm | **48 passed in 3.85s**. Source test PR #22 vẫn giữ nguyên, chưa thể ghi bản gốc 48/48 pass. |
| Flutter | **28 passed, 0 failed, 0 skipped**; analyzer `No issues found`; release build đạt với `--no-web-resources-cdn`. |
| Web release → Uvicorn → Teacher thật | **9 nhóm tình huống đạt**, không mock prediction; không page error hoặc request tới website đích. |

Hai skip của môi trường QA này:

- `test_brand_regressions.py`: bộ tham số brand rỗng.
- `test_splits.py`: chưa có handoff dữ liệu local từ notebook 02/03.

So với **554 passed, 1 skip** trong bàn giao của Hưng, lần chạy full PR #22 tại đây chuyển một ca thành skip do thiếu handoff local và có thêm một failure bootstrap Windows. Không chạy notebook hoặc sửa test chỉ để khớp số đếm.

## Tích hợp Teacher và contract

Blocker cũ `QA-TEACHER-01` đã được mở trên bản backend mới: mode `teacher` gọi `load_teacher(repo_root)` chính thức, warm-up xong mới ready; `/health` trả `status=ok`, `model_ready=true`, model/hash/protocol đúng release lock.

Bộ QA hiện kiểm tra release lock/promotion/hash/runtime; Python single/batch/CLI và API parity trên **13 input**, tolerance score tuyệt đối `1e-12`. Các input gồm thiếu scheme, hostname case, Unicode/punycode, IPv4/IPv6, port hợp lệ, path/query/escaping, userinfo/fragment và biên 4096 ký tự. API trim khoảng trắng ngoài trước khi chuyển chuỗi vào adapter theo contract v1.

Nhãn của Teacher theo `score >= threshold`; score meta-LR chưa calibrated. Đã kiểm tra độc lập trường hợp score `0.5760558654872864` vẫn có nhãn benign vì thấp hơn ngưỡng lock. Không dùng .5 để suy nhãn; không biểu diễn score thành phần trăm an toàn.

Các ca bảo mật chặn DNS/socket, bắt log từ DEBUG, kiểm tra không lộ raw URL/secret/traceback, guards artifact/version/hash/runtime và lỗi response được chạy lại. Công cụ latency được cập nhật để kiểm tra cả `estimator.predict` và rule threshold, đồng thời lưu rule/threshold trong kết quả.

## Latency bằng Teacher thật

- Uvicorn một process, loopback, `--no-access-log`, `OMP_NUM_THREADS=1`; client HTTP/1.1 keep-alive, concurrency 1.
- 10 request warm-up, **100 request đo**, tất cả HTTP 200 và đúng contract/model metadata.
- Mean **16.0741 ms**, p95 nearest-rank **19.8404 ms**.
- Cấu hình/runtime/artifact trong `tables/week6/api_latency_teacher.json`; không lưu raw URL. Đây là phép đo trên máy QA, không phải cam kết latency cho mọi máy hoặc tải đồng thời.
- Số đo tổng hợp cũ trong `api_latency_synthetic.json` được giữ làm lịch sử.

## Final E2E bằng model thật

| Tình huống | Kết quả |
| --- | --- |
| URL rỗng | Validation ở Web, không POST. |
| URL hợp lệ, thiếu scheme | HTTP 200; nhãn, score và model hiển thị đúng backend. |
| Benign với score > .5 | Score 0.576056 trên UI; nhãn benign đúng threshold lock. |
| Phishing từ ví dụ Hưng bàn giao | HTTP 200, score 0.9319661170520045; UI có cảnh báo phishing. Dùng lại mẫu ID `024efd11-58b4-57c4-8d40-383a1034b19f` được bàn giao; không mở website đích hoặc tạo benchmark mới. |
| URL sai port | HTTP 422 `invalid_port`; UI có thông báo lỗi, input sửa được. |
| Thiếu model | Restart server với release root rỗng: HTTP 503 `artifact_missing`; UI báo model chưa sẵn sàng. Artifact chính thức giữ nguyên. |
| Backend mất kết nối | Dừng process Uvicorn thật; Web kết thúc loading và báo lỗi kết nối. |
| Phục hồi/retry | Khởi động lại đúng model/port; retry thành công trên cùng trang, không reload. |
| Responsive | 390×844, 320×844, 844×390, 768×1024, 1440×900 không overflow ngang của document. Đây là viewport emulation, không phải test Android vật lý. |

Bằng chứng: `tables/week6/release_e2e.json` và ảnh `figures/week6/khiem_teacher_{valid,phishing,invalid,unavailable,offline,mobile}.png`. Chỉ gọi HTTP loopback tới Web/API; prediction không bị route-mock.

## Review cần Hưng xử lý — QA-WIN-01

`tests/test_api_teacher.py::test_real_released_teacher_warmup_and_prediction_are_offline` monkeypatch `socket.socket.connect` trước khi tạo TestClient. Trên CPython 3.11 Windows, event loop khởi tạo self-pipe bằng `socket._fallback_socketpair`, cần connect loopback nội bộ. Test chặn kết nối này và fail **trước khi gọi loader/warm-up Teacher**.

Đề nghị dời việc chặn `connect`/`connect_ex` vào wrapper của `teacher_module.load_teacher`: event loop đã được tạo, còn loader/warm-up/predict vẫn chịu network guards. Đề xuất đã kiểm bằng bản sao test và đạt 48/48. Phản hồi trực tiếp tại dòng 100 của `tests/test_api_teacher.py` trên review PR #22.

Backend thật đã chạy được; tuy nhiên PR #22 nguyên bản chưa đạt tất cả test trên Windows. Chờ Hưng cập nhật test rồi chạy lại trước khi approve theo yêu cầu nghiệm thu này.

## Trạng thái Issue #17 và bước chốt

| Hạng mục | Trạng thái |
| --- | --- |
| Contract, URL cases, artifact errors | Đạt trong suite QA trên backend mới. |
| API–Python/CLI parity | Đạt trên Teacher phát hành, 13 input, atol 1e-12. |
| Security và mất kết nối | Đạt trong các test QA và browser smoke đã chạy. |
| Latency Teacher thật | Đã có mean/p95, runtime/hash/cấu hình thực tế. |
| Final E2E Web → API → Teacher | Đã có kết quả đủ ba tình huống bắt buộc và các ca bổ sung trên revisions nêu trên. |
| Review PR22 | Còn QA-WIN-01; không đổi failure thành pass hoặc skip. |
| Review PR23 | Chưa thấy lỗi trong 28 tests/analyze/build và các ca browser đã kiểm. |
| CI phần QA mới | Workflow đã pin backend/Teacher phát hành và bật API acceptance; **chưa push/chạy Actions cho diff này**. |
| Clean clone revision QA cuối | Baseline `cef4aea` đã có 439 passed/2 skipped và smoke không model. **Cần chạy lại sau khi commit/merge/push revision cuối**; chưa nhận hoàn tất phần này. |

Nhánh QA còn thay đổi chưa commit. Trong lần kiểm này, venv QA cài source API từ checkout PR #22; không copy đè code backend/Web/model vào diff QA. Sau khi người phụ trách tự commit phần QA, cập nhật nhánh bằng merge backend mới, kiểm lại source import/pytest/Actions và clean clone đúng SHA cuối. Giữ deadline tests/security/CI/clean clone 14/11/2026; bằng chứng E2E phải gắn với revisions cuối trước nghiệm thu 15/11.

## Lịch sử và tái lập

Hướng dẫn lệnh hiện tại: `tests/README.md`. Bằng chứng tổng hợp hiện tại: `tables/week6/release_review.json`. Báo cáo trước khi Teacher stacking được phát hành nằm ở `history/week6_api_qa_pre_release.md`; `teacher_integration.json` giữ bằng chứng v1/candidate cũ. Những trạng thái chờ Teacher v1/candidate trong lịch sử không phải trạng thái của lần kiểm hiện tại.
