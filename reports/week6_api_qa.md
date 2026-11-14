# Báo cáo QA API — Issue #17

Cập nhật ngày **14/11/2026**, múi giờ Asia/Ho_Chi_Minh. Nghiệm thu code tại **`441a88cd686a7fc4a84a0dd8991960804b7e5625`**: CI 4/4 success và clean clone đúng SHA đã đạt. Báo cáo giữ riêng các lần kiểm lịch sử trước khi commit.

## Phiên bản và phạm vi

- QA đã merge và push: `441a88cd686a7fc4a84a0dd8991960804b7e5625`, nhánh `test/api-contract-qa`; commit QA trước đó là `b0d448d`.
- Backend PR #22 đã sửa QA-WIN-01: `bbc9eaeecb3c80beba9e099f539731e6c72b97b1`.
- Người phụ trách đã hoàn tất merge và xử lý conflict cấu hình/hướng dẫn. Code/config/tests công bố khớp chính xác bản candidate đã kiểm; không còn merge đang chờ xử lý.
- Web PR #23: `a2bb0dcedb7d12777774462a5fdea680aca2ff7e`, chưa có commit mới so với lần browser E2E.
- Teacher release: `398ee2c`, đã có trên main `7d2d600`; model `teacher-stacking-v2`, preprocessing `canonical-reference-v1`, `promoted=true`.
- Bundle giữ tên lịch sử `models/teacher_v2_candidate.joblib`; SHA256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`.
- Ngưỡng từ release lock `0.6945740700635259`; rule `score >= threshold`. Score meta-LR chưa calibrated, không phải phần trăm an toàn.
- Windows build 26200, CPython **3.11.14**, libraries khớp `requirements-teacher.txt`. Không sửa source backend/Web, bundle, lock, data, folds, reference hoặc notebook của upstream. Các file upstream được đưa vào bằng merge nguyên trạng.

## Kết quả kiểm thử

| Phạm vi | Kết quả thực tế |
| --- | --- |
| Nhánh QA đã hợp nhất, cài source tại chính checkout, có research dependencies | **624 passed, 2 skipped, 1 deselected in 93.02s**; không fail/error. |
| PR #22 nguyên bản tại `bbc9eae`, API/Teacher | **48 passed in 5.62s** trên Windows; QA-WIN-01 không còn tái hiện. |
| PR #22 nguyên bản, full available suite | **553 passed, 2 skipped, 1 deselected in 77.09s**. |
| Clean clone commit QA đã push `b0d448d`, source backend `7dfeec5` theo workflow của commit đó | **490 passed, 2 skipped**; venv mới, pip check đạt, backend Teacher thật startup/health/predict đạt. |
| Bản merge candidate trong clone sạch, runtime API/teacher theo workflow mới | **597 passed, 3 skipped, 1 deselected**; không fail/error. |
| Clean clone code công bố `441a88c`, venv mới độc lập | **597 passed, 3 skipped, 1 deselected**; pip check đạt, startup/health/predict bằng Teacher thật đạt. |
| Gate Teacher API riêng trong clone sạch `441a88c` | **15 passed, 0 skipped**; các bài Teacher không bị bỏ qua. |
| Flutter/Web đã kiểm tại `a2bb0dc` | **28 passed**, analyze không lỗi, release build đạt; browser thật đạt **9 nhóm tình huống**. |

Hai skip lịch sử: bộ tham số brand regression rỗng và thiếu handoff local notebook 02/03. Clone sạch với extras API/teacher có thêm một skip collection `test_url_research.py` vì không cài Torch/Transformers. Nhóm nghiên cứu này đã được chạy trong môi trường đầy đủ của lần **624 passed**; workflow nghiên cứu upstream được giữ nguyên. Không chạy notebook để khớp số đếm.

Lệnh full QA loại đúng `test_real_external_bundle_matches_saved_scores` theo phạm vi công việc, không tắt assertion hoặc chuyển lỗi thành skip. Warnings còn lại là deprecation có sẵn ở pandas/sklearn và escape sequence `week5_reporting.py`. Số pass khác nhau do revision, các test QA bổ sung và extras thực sự được cài.

## Contract, parity và security

Đã kiểm GET `/health`, POST `/predict`, URL rỗng/thiếu dữ liệu, thiếu scheme, Unicode/punycode, IPv4/IPv6, port lỗi, URL dài và biên 4096 ký tự. Các trường hợp thiếu model, artifact/version/hash/runtime không tương thích có kiểm tra error envelope và readiness.

Teacher integration có **32 bài**, gồm Python single/batch/CLI và API parity trên **13 input**, sai số tuyệt đối `1e-12`; API trim khoảng trắng ngoài theo contract. Nhãn theo threshold trong lock; ca score `0.5760558654872864` vẫn benign được kiểm riêng.

Các test chặn DNS/socket, kiểm log từ DEBUG, không lộ raw URL/secret/traceback, cùng các trường hợp lỗi kết nối và response sai đều đã chạy. QA-WIN-01 được Hưng sửa bằng cách đặt network guards trong wrapper `load_teacher`, sau khi event loop của TestClient khởi tạo, vẫn bảo vệ load/warm-up/predict và giữ nguyên assertions.

## Latency Teacher thật

Đo lại trong môi trường clone sạch với một Uvicorn process, `--no-access-log`, `OMP_NUM_THREADS=1`, HTTP/1.1 keep-alive, concurrency 1. **10 warm-up và 100 request đo**, tất cả HTTP 200 và metadata/contract hợp lệ.

- Mean **12.4201 ms**; p95 nearest-rank **13.3468 ms**.
- Runtime, artifact, rule, threshold và số request: `tables/week6/api_latency_teacher.json`.
- Lần đo trước: mean 16.0741 ms, p95 19.8404 ms; khác biệt do lần chạy/môi trường, không coi là cải thiện model. Không có SLO được đặt hoặc kết luận hiệu năng cho mọi tải.

## CI và clean clone

Commit **`441a88c` đạt 4/4 checks**: [push run 43555760391](https://github.com/phuctran33/PhishGuardVN/actions/runs/43555760391) và [pull_request run 43555764634](https://github.com/phuctran33/PhishGuardVN/actions/runs/43555764634), mỗi run gồm Windows và Ubuntu. Đã đọc trạng thái từng job và xác nhận cả `Run test suite` lẫn `Teacher API acceptance` đều success, không skip. CI cũ tại `b0d448d` được giữ trong JSON lịch sử.

Workflow dùng source ngay trong checkout, matrix **Windows/Ubuntu, CPython 3.11**, runtime khóa phiên bản, gate Teacher API không skip và upload JUnit. Cả bốn jobs của bản merge công bố đều thành công.

Clean clone đã thực hiện bằng clone mới từ GitHub, venv mới không system-site-packages, model/lock từ Git, không chép handoff dữ liệu hoặc model cache local. Đã cài dependencies theo hướng dẫn, chạy `pip check`, pytest, startup Uvicorn thật, GET health **200/ok/model_ready=true**, POST hợp lệ **200**, port lỗi **422/invalid_port**, và dừng server sau kiểm tra.

Sau khi push, đã clone mới từ GitHub, checkout đúng **`441a88c`**, tạo một venv CPython 3.11 mới và cài theo README. Không dùng venv của lần candidate. Kết quả **597 passed, 3 skipped, 1 deselected**, gate Teacher **15 passed/0 skipped**; health 200/ready, predict 200, invalid port 422. Checkout giữ sạch sau kiểm thử. Code/config/tests khớp patch candidate `d2ff546c0f2252f6f311fc12270b21cb3c5100536e89ad725d0b12be8bd6c7e1`. Lệnh, runtime, revision, artifact và kết quả CI trong `tables/week6/clean_clone.json`.

## E2E Web → API → model thật

Bằng chứng đã chạy gồm URL hợp lệ/thiếu scheme, benign có score trên .5, mẫu phishing đã bàn giao, URL rỗng không POST, port sai/422, thiếu model/503, dừng backend thật và retry sau restart trên cùng trang, cùng 5 viewport. **9 nhóm tình huống đạt**, không mock prediction, không request tới website đích, không page error. Viewport emulation không phải Android vật lý.

Ảnh và JSON tại `figures/week6/khiem_teacher_*.png`, `tables/week6/release_e2e.json`. Lần browser thực tế dùng backend `7dfeec5`; `bbc9eae` chỉ sửa test. Đã đối chiếu hash source API/release lock/Web client/UI không đổi, không sửa revision trong bằng chứng cũ để giả thành lần chạy mới.

## Chốt đầu việc hạn 14/11

| Hạng mục | Trạng thái |
| --- | --- |
| Contract, URL cases, lỗi artifact/runtime | Đã kiểm trên Teacher phát hành, không fail. |
| API–Python/CLI parity, security, lỗi mất kết nối | Đạt trong tests và browser đã chạy. |
| Latency mean/p95 và cấu hình/artifact | Đã có số đo Teacher thật trong clone sạch. |
| Hướng dẫn chạy và báo cáo lỗi | Đã cập nhật `tests/README.md` và bằng chứng JSON. |
| CI code công bố | `441a88c` **4/4 success**, đủ hai OS và hai sự kiện. |
| Clean clone | **Đạt tại `441a88c`**, venv mới, đủ install/pip check/pytest/backend/health/predict và lý do skip. |
| Dependency Hưng/Phúc | Không còn blocker code/artifact được biết trong phạm vi đã kiểm. |
| Final E2E trước nghiệm thu 15/11 | Đã có đủ ba tình huống bắt buộc với Teacher thật, kèm các ca bổ sung. |

Các hạng mục kỹ thuật của Issue #17 đã có bằng chứng nghiệm thu tại **`441a88c`**, không còn blocker đã biết trong phạm vi được giao. Người phụ trách tự commit/push bản cập nhật báo cáo này và ghi kết quả vào Issue #17 để nhóm nghiệm thu. Đây là cập nhật bằng chứng, không thay code/model/config/tests đã kiểm; không cần lặp clean clone chỉ vì bổ sung báo cáo. Không tự merge PR hoặc đóng issue thay người phụ trách.

Lịch sử v1/candidate: `history/week6_api_qa_pre_release.md`, `tables/week6/teacher_integration.json`. Kết quả hiện tại: `tables/week6/release_review.json`; không dùng trạng thái chờ trong lịch sử để mô tả bản release hiện tại.
