# Lịch sử QA trước khi backend tích hợp Teacher stacking phát hành

Đây là snapshot lịch sử. Trạng thái và lệnh hiện tại nằm ở `../week6_api_qa.md` và `../../tests/README.md`.

## Phạm vi và môi trường

- Nhánh kiểm tra: `test/api-contract-qa`, dựa trên nhánh backend PR #22.
- Giai đoạn kiểm thử: 10–13/11/2026; bổ sung bàn giao Teacher PR #24 ngày 13/11.
- Hệ điều hành: Windows, chạy bằng PowerShell.
- Python: 3.13.7.
- Gói được cài từ `pyproject.toml` với extra `api,test`; phần Teacher thêm extra `teacher-qa` để dùng đúng `scikit-learn==1.9.1`. `tldextract` 5.4.0 và `idna` 3.20.
- Test contract API cũ dùng estimator/artifact tổng hợp; test Python/CLI Teacher mới dùng bundle thật từ checkout PR #24 được khóa SHA. Source và artifact của Phúc được giữ trong checkout riêng, không copy vào diff QA.
- Teacher hiện tại là raw-URL TF-IDF SVM, không dùng file E2 `week5_e2_ablation.joblib` hoặc MLP lịch sử `week6_teacher_v1.joblib`.

## Kết quả

Các số dưới đây ghi rõ từng lần chạy. Sau khi dùng `--basetemp` riêng, Khiêm đã tự xác nhận từ terminal: **472 passed, 3 skipped in 43.13s**. Kết quả khớp lần chạy của agent (**472 passed, 3 skipped in 43.67s**). Bài nghiệm thu API Teacher chạy riêng vẫn thất bại do `artifact_incompatible`, chưa đạt tích hợp.

- `tests/test_api.py`: **43 passed** trong lần chạy lại working tree ngày 13/11/2026.
- `tests/test_api_benchmark.py`: baseline **2 passed**; sau bổ sung có **11 ca**, đều đã qua trong full suite mới nhất.
- Baseline tại `cef4aea`: **439 passed, 2 skipped**; clean clone xác nhận cùng kết quả.
- Bổ sung Teacher Python/CLI: **24 passed, 1 deselected**. Full suite có `--teacher-root` cho kết quả **463 passed, 3 skipped in 39.26s**.
- Sau các hiệu chỉnh cuối: full suite **472 passed, 3 skipped in 43.67s**, dùng thư mục `--basetemp` mới cho lần chạy. API contract suite có 43 ca; benchmark suite có 11 ca; Teacher Python/CLI có 24 ca. Ba skip giữ nguyên: brand fixture, handoff notebook và API acceptance chạy riêng.
- Nghiệm thu API với Teacher thật, chạy riêng bằng `--teacher-api -m teacher_api`: **1 failed, 24 deselected** do backend chưa load được bundle. Full suite mặc định skip ca này; skip không được tính là nghiệm thu API đã đạt.
- `pip check`: không có dependency lỗi.
- `git diff --check`: không có lỗi whitespace.

Hai skip của baseline:

- `tests/test_brand_regressions.py:58`: fixture không sinh ra bộ tham số brand regression.
- `tests/test_splits.py:210`: chưa có handoff dữ liệu local từ notebook 02 và 03.

Các số **419/2**, **420/1** trong các lần kiểm tra PR #22 và **439/2** của baseline QA thuộc revision/môi trường và tập test khác nhau. Ghi kèm SHA, môi trường và handoff khi so sánh. Khi cấu hình Teacher, skip thứ ba là ca nghiệm thu API chưa bật; ca đó đã được chạy riêng và thất bại như nêu trên.

Lúc chuẩn bị môi trường QA, full suite ban đầu báo thiếu `nbformat`, sau đó các test notebook báo thiếu `IPython`. Hai gói đã được khai báo trong extra `test` và cài vào môi trường; chạy lại full suite cho kết quả nêu trên.

## Kiểm tra đã bổ sung

- Body sai kiểu, URL rỗng, URL dài quá giới hạn, URL đúng 4096 ký tự và khoảng trắng đầu/cuối.
- URL hợp lệ/lỗi theo parser, gồm Unicode, IPv4/IPv6, port lỗi và hostname lỗi.
- Model/artifact chưa sẵn sàng, artifact lỗi hoặc metadata không tương thích.
- Lỗi inference/lỗi nội bộ được che chi tiết; kiểm tra không lộ URL nhạy cảm, exception hoặc traceback.
- Chặn DNS/socket trong test xử lý URL để kiểm tra luồng offline; kiểm tra raw URL không xuất hiện trong log khi request thành công.
- So sánh response API với `predict_url` và `scripts/predict_week5.py` trên cùng artifact tổng hợp. Đây **không phải** parity với model thật.

## Bổ sung kiểm chứng ngày 11/11/2026

### CI và clean clone

- GitHub Actions `Python tests` thành công trên push commit `2a3efeb` và lần đồng bộ PR #25. Bốn ca pytest bổ sung ghi ở phần dưới được thêm sau commit này, nên cần push để CI chạy lại.
- Tạo clone mới từ branch QA đã push; SHA của branch GitHub được xác minh là `2a3efebcc9cc4c6c21a65511a8c7498d6bc0dc69`.
- Môi trường clone sạch: Windows 11, Python 3.13.7; cài theo `docs/backend.md` với `.[api,test]`, `tldextract==5.4.0`, `idna==3.20`; `pip check` không có dependency lỗi.
- Full pytest trong clone: **435 passed, 2 skipped, 1 SyntaxWarning**. Skip vẫn là thiếu handoff dữ liệu notebook 02/03 và bộ tham số brand regression; warning `invalid escape sequence` ở `src/phishguard_vn/week5_reporting.py:148`.
- Chạy Uvicorn tại `127.0.0.1:8013` với `--no-access-log`, không cấu hình artifact: `/health` trả 200 `degraded/not_configured`; POST URL hợp lệ trả 503 `MODEL_UNAVAILABLE/not_configured`; URL sai port trả 422 `INVALID_URL/invalid_port`.
- Các request HTTP trong lần kiểm tra PowerShell được gửi bằng `curl.exe` và file JSON UTF-8 qua `--data-binary`, tránh khác biệt quote/alias của PowerShell.

### Kiểm tra bổ sung trong working tree

- Thêm test so sánh API với `scripts/predict_week5.py` trên **cùng artifact tổng hợp và cùng input**; test log raw URL; thêm `scripts/benchmark_api_latency.py` và hai test cho kết quả JSON/bảo vệ trạng thái model chưa sẵn sàng.
- Sau các test bổ sung: API suite **43 passed**; toàn bộ suite **439 passed, 2 skipped** trên Python 3.13.7. Các thay đổi sau commit `2a3efeb` chưa được commit/push ở thời điểm ghi báo cáo, vì vậy chưa nằm trong CI run.

### Đo latency thử nghiệm

- Đo HTTP qua Uvicorn loopback bằng `scripts/benchmark_api_latency.py`, với 10 request warm-up và 100 request đo, HTTP/1.1 keep-alive; Windows 11, Python 3.13.7, FastAPI 0.162.4, Uvicorn 0.54.0.
- Artifact SHA256 `d50f7377652d36f4ab770ce3ef499bb683dd8e28a3437c0c67804e8fc1c92f7a`, model `DummyClassifier`, feature set `lexical_12`, protocol `synthetic-latency-only`.
- Kết quả thử nghiệm: **mean 3.806 ms, p95 4.362 ms** (nearest-rank). JSON cấu hình/kết quả: `reports/tables/week6/api_latency_synthetic.json`. Đây chỉ là baseline của API với artifact tổng hợp; **không đại diện latency model thật và không thay kết quả benchmark cuối**.
- Đã xác nhận script từ chối đo nếu `/health.model_ready` là false; trường hợp không có model kết thúc với exit code 2 và không ghi file kết quả.

## Xác minh bổ sung ngày 13/11/2026

- Chạy lại full pytest trên working tree hiện tại: **439 passed, 2 skipped** trong 44,24 giây. Hai skip giữ nguyên lý do đã nêu; lần chạy này không có warning.
- PR #23: `flutter analyze --no-pub` báo `No issues found`; `flutter test --no-pub` có **19 tests passed**; `flutter build web --release --no-pub` thành công.
- Thử smoke Web → API với artifact tổng hợp `DummyClassifier`, protocol `mock-e2e-only`; API chỉ bind loopback `127.0.0.1:8015`, CORS cho origin `http://127.0.0.1:3000`. Trang Web báo API sẵn sàng; gửi một URL hợp lệ qua form cho kết quả `phishing`, điểm `100.00%` từ model giả.
- Smoke trên chỉ xác nhận luồng HTTP/UI cơ bản với model giả. Không xem đó là Teacher, kết quả đánh giá model hay final E2E với model thật. URL port lỗi và backend offline được kiểm tra trong contract/widget tests; lần smoke trình duyệt này không xác nhận riêng hai tình huống đó.

### CI và clean clone trên revision đã push

- Commit QA: `cef4aea917711188931c0849f5caee9911c70ff4`. GitHub Actions hiển thị **2/2 checks passed** cho commit này.
- Clean clone xác nhận đúng SHA trên; môi trường Windows 11, build 26200, Python 3.13.7.
- `pip check`: `No broken requirements found`.
- Full pytest: **439 passed, 2 skipped in 42.50s**. Skip tại `tests/test_brand_regressions.py:58` do tập tham số rỗng; skip tại `tests/test_splits.py:210` do thiếu handoff dữ liệu notebook 02/03.
- Uvicorn chạy trên `127.0.0.1:8000` với access log tắt và không cấu hình model. `GET /health` trả HTTP 200, `degraded`, `model_ready=false`, `model_error=not_configured`. POST URL hợp lệ gửi bằng `curl.exe` với JSON UTF-8 trả HTTP 503 `MODEL_UNAVAILABLE/not_configured`, đúng contract khi clone không có artifact.
- Đây là kiểm chứng clean clone cho backend không model; chưa phải kiểm thử inference với Teacher.

## Tích hợp bàn giao Teacher PR #24 ngày 13/11/2026

### Artifact và kết quả Python/CLI

- Source bàn giao: `35c7d8d1b6c7e907aaa539ca145b3abacf1cba7f`; đã đối chiếu với head PR #24 trên remote. Lock ghi `teacher_finalized=true`, model `tfidf_linear_svm`, feature set `url_raw_char_3_5`, model version `teacher-tfidf-svm-v1`, preprocessing `raw-char-3-5-v1`.
- Bundle: `models/teacher_tfidf_svm_v1.joblib`, SHA256 `5a6d9b500ee147ae2f6cc78f986ac3122658eab58dfd9ad636f11d0ba19494b5`. Metadata SHA256 `999d03349d7ca879fbdeed6e8afab0fdd533f853706ef78c9def74c0bd2095e7`. Cả hai khớp lock.
- `tests/test_teacher_integration.py` kiểm tra loader thật, single/batch/CLI parity từ working directory khác, nhãn từ `estimator.predict`, signed margin, giữ nguyên chuỗi raw, Unicode/IDNA/IP/port/URL dài, input lỗi, hash/version/runtime sai và không gọi DNS/socket hoặc log raw input.
- Kết quả focused: **24 passed, 1 deselected**. Full suite cấu hình Teacher: **463 passed, 3 skipped**. Ca API nghiệm thu được chạy riêng, không tính skip mặc định là pass.
- Runtime local: Python 3.13.7, scikit-learn 1.9.1, numpy 2.5.4, scipy 1.18.1, joblib 1.6.0. Loader yêu cầu đúng scikit-learn 1.9.1; các versions khác được ghi lại để đối chiếu.

### Blocker QA-TEACHER-01: backend chưa nhận bundle raw-URL

- Head backend PR #22 trên remote vẫn là `509e6a3cb93fd64a8fa459cd8173e90f9ed045a4`. Factory/loader hiện hỗ trợ lexical/E2 và yêu cầu feature order/model container của bundle v2; bundle Teacher mới chứa pipeline TF-IDF/LinearSVC nên bị từ chối.
- Đã chạy cả TestClient và Uvicorn HTTP loopback bằng bundle thật, đúng hash và model name. `/health` trả 200 nhưng `degraded`, `model_ready=false`, `model_error=artifact_incompatible`; POST URL hợp lệ trả 503 `MODEL_UNAVAILABLE/artifact_incompatible`. Khác với clean clone không model có reason `not_configured`.
- Lệnh nghiệm thu `--teacher-api -m teacher_api` cho **1 failed** tại assertion model readiness. Parity API–CLI của Teacher chưa chạy được, không nhận pass.
- Công cụ benchmark chạy trên backend này trả exit code **2**, từ chối đo và không tạo file latency Teacher. Baseline tổng hợp cũ vẫn được giữ nguyên, chưa có mean/p95 API của Teacher thật.
- Giao thức cũng cần Hưng thống nhất: Teacher nhận raw URL nguyên trạng, không strip/lower/normalize/truncate; API v1 hiện trim và parser kiểm tra port/độ dài. Không đổi các assertions v1 hoặc sửa backend để che khác biệt. Cần loader/config và quyết định contract từ phụ trách backend trước khi chốt bài nghiệm thu mới.
- Bằng chứng máy đọc được: `reports/tables/week6/teacher_integration.json`. Không sửa Teacher, parser/features, model bytes, lock, dữ liệu hoặc các báo cáo benchmark của Phúc.

### Đầu vào cần Hưng bàn giao để kiểm thử tiếp

- Nhánh và commit backend hỗ trợ `models/teacher_tfidf_svm_v1.joblib` từ PR #24, cùng lệnh cài/chạy và cấu hình model, bundle format, hash/lock thực tế. Backend thuộc PR #22; PR #23 là Flutter Web.
- Contract cập nhật về xử lý URL: giữ nguyên raw input hay có bước trim/kiểm tra parser, giới hạn độ dài và quy tắc lỗi. Response cần nêu rõ signed SVM margin với `score_kind=decision_function`, không diễn giải thành xác suất.
- Xác nhận Web PR #23 tương thích response mới; nếu cần sửa Web thì cung cấp commit và lệnh chạy tương ứng, gồm cấu hình CORS/base URL.
- Sau bàn giao, cập nhật QA theo contract được thống nhất rồi chạy gate API Teacher, API–CLI parity, latency thật, CI và clean clone trên revision cuối. Final E2E chạy theo ba tình huống trong `tests/README.md`; ghi kết quả từng tình huống trước nghiệm thu 15/11.

## Kiểm tra tùy chọn PR #26: Teacher v2 candidate

- Source kiểm tra: `1b07af3debd225efafb04b06d3af82af65e8b38a`, checkout riêng PR #26. Lock ghi `candidate_only=true`, `promoted=false`. Teacher v1 vẫn là mặc định; bundle/lock/loader/CLI/metadata v1 có hash giống PR #24. Pin Teacher của bộ QA được giữ tại PR #24.
- Candidate: `models/teacher_v2_candidate.joblib`, 2.130.586 bytes; SHA256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`, khớp lock. Model version `teacher-stacking-v2-candidate`; preprocessing `canonical-reference-v1`; ngưỡng `0.6945740700635259`. Score meta-LR chưa calibrated, không diễn giải là phần trăm an toàn.
- Venv riêng cài đúng toàn bộ `runtime_versions` của candidate lock và LightGBM 4.7.0 cho fixture test. `pip check` đạt. Suite `tests/test_stacking.py`: **53 passed in 13.94s**, JUnit xác nhận 53 ca, 0 skip/failure/error.
- Kiểm thêm bundle thật với năm URL ví dụ chính thức trong thư mục portable chỉ có runtime/model/lock/CLI, không chứa dataset/report/reference CSV. CLI so với Python batch có score delta **0**; single/batch delta tối đa **1.6653345369377348e-16**, trong tolerance `1e-12`; nhãn khớp quy tắc threshold. Chặn DNS/socket khi kiểm tra: **0 lần gọi**.
- Phạm vi kiểm lại là 53 fixture tests và inference portable năm URL bằng bundle thật. Số full research suite/OOF/metrics trong PR #26 là kết quả của người bàn giao, chưa được tái chạy trong lần QA này.
- Đối chiếu remote cùng lần kiểm: PR #22 vẫn ở `509e6a3cb93fd64a8fa459cd8173e90f9ed045a4`, PR #23 vẫn ở `3c90552509cfb5dfa38ca896b866033d0cc0998b`. Candidate v2 chưa promoted và không bổ sung backend; blocker QA-TEACHER-01 của Teacher v1 vẫn cần Hưng xử lý.

## Trạng thái còn lại

- Teacher/artifact đã nhận và đã kiểm chứng Python/CLI thật. API parity, API latency và final E2E model thật đang bị chặn bởi QA-TEACHER-01, cần Hưng bàn giao backend/config/contract hỗ trợ raw-URL Teacher.
- Workflow CI được bổ sung checkout Teacher tại SHA cố định, chạy full suite với `--teacher-root` rồi chạy riêng gate `Teacher API acceptance` bằng `--teacher-api`. Gate không bỏ qua failure, nên backend hiện tại sẽ làm check fail. Chưa có Actions run cho các thay đổi chưa commit này. CI xanh **2/2** và clean clone **439/2** tại `cef4aea` là bằng chứng baseline, chưa chứng minh phần Teacher mới.
- Sau khi bạn commit/push phần mới, kiểm tra Actions và chạy clean clone có cấu hình Teacher theo README. Test nghiệm thu API vẫn phải được chạy rõ bằng `--teacher-api`; không được xem suite xanh do skip ca này là hoàn tất tích hợp.
- Smoke Web → API với model giả đã có; ba tình huống final smoke Web → API → model thật cần chạy sau khi backend tương thích và Web ổn định.

## Đối chiếu toàn bộ Issue #17

| Hạng mục | Bằng chứng và trạng thái |
| --- | --- |
| GET /health, POST /predict; URL rỗng, thiếu scheme, Unicode, IP, port, URL dài | 43 API tests đã qua theo contract v1, bao gồm các guards log cập nhật trong full suite 472/3 do Khiêm tự chạy. |
| Thiếu model, artifact/version/hash không hợp lệ | Đã có test baseline và test Teacher thật. Teacher thật bị backend từ chối: blocker QA-TEACHER-01. |
| API so với Python CLI cùng artifact/input | Synthetic API–CLI đã qua; Python single/batch/CLI Teacher thật đã qua. API–CLI Teacher thật chưa đạt vì API không ready. |
| Không truy cập URL đích, không lộ traceback/secrets/raw URL | Network/log/error tests, bắt log DEBUG/INFO và chặn connect_ex đã qua trong full suite 472/3; có kiểm tra offline/log riêng với Teacher Python thật. Chưa nghiệm thu qua API Teacher. |
| Mất kết nối/tình huống tích hợp | Flutter HTTP mock có offline/retry; test benchmark mất kết nối và response sai contract đã qua trong full suite do Khiêm tự chạy. Final E2E vẫn chưa đủ ba tình huống. |
| API latency mean/p95 và cấu hình/artifact | Chỉ có baseline tổng hợp. Latency Teacher thật bị chặn; công cụ trả exit 2 và không tạo số đo. Chưa hoàn tất. |
| GitHub Actions | Baseline cef4aea có 2/2 checks passed. Workflow mới chưa push; gate Teacher API hiện tái hiện failure và phải được báo đỏ. |
| Hướng dẫn test và báo cáo lỗi | Đã cập nhật README/báo cáo, JSON bằng chứng và checklist final E2E trong working tree. Khiêm đã tự kiểm suite và tái hiện blocker API; thay đổi chưa commit. |
| Clean clone trước 14/11 | Đã có bằng chứng cef4aea, 439 passed/2 skipped, backend/health/503 không model. Cần chạy lại revision mới sau commit/push để bao phủ thay đổi mới. |
| Final E2E trước nghiệm thu 15/11 | Chưa hoàn tất. Mới có widget mock tests và một smoke URL hợp lệ dùng mock model. Cần Web → API → model thật: URL hợp lệ, URL sai, backend mất kết nối. |

**Kết luận:** Issue #17 chưa đạt Definition of Done đầy đủ. Phần đang bị chặn là API Teacher/parity/latency và final E2E model thật; không chuyển sang pass chỉ vì suite mặc định skip gate. Deadline tests/security/CI/clean clone ngày 14/11 không thay đổi. Phản hồi QA-TEACHER-01 cho phụ trách PR #22 để có loader/config và contract cập nhật; báo cáo blocker trong Issue #17 trước deadline.

### Hiệu chỉnh sau rà soát cuối

- Test security bắt log từ DEBUG trở lên để không bỏ sót raw URL ở INFO/DEBUG; bổ sung chặn `socket.connect_ex`.
- Benchmark kiểm tra response thành công theo contract, identity model/protocol và score hữu hạn; xử lý lỗi HTTP bị ngắt mà không in traceback, không tạo file kết quả mới.
- Bổ sung chín ca benchmark cho response 200 sai contract, signed margin, mất kết nối, health sai kiểu và cách tính p95 nearest-rank. Các ca mới đã qua trong lần full suite 472/3 bằng temp riêng.
- CI có gate Teacher API riêng không bỏ qua lỗi. Backend hiện tại được dự kiến fail gate này; phải sửa dependency backend rồi nghiệm thu lại, không đổi test để che lỗi.
- Sau khi Khiêm báo 134 errors, agent tái kiểm full suite bằng temp riêng: **472 passed, 3 skipped**; API nghiệm thu riêng **1 failed, 24 deselected in 2.41s**. Khiêm sau đó đã tự chạy lại: full suite **472 passed, 3 skipped in 43.13s**; API nghiệm thu **1 failed, 24 deselected in 2.44s**, cùng lý do `artifact_incompatible`. Chưa commit/stage.

### Phân loại lần chạy có 134 errors

- Lần chạy terminal người dùng: **338 passed, 3 skipped, 134 errors**. Traceback gửi lại nằm ở `_pytest/tmpdir.py → getbasetemp → make_numbered_dir → find_suffixes`, trước khi thực thi test.
- Collection có đúng **134 test cần fixture tmp_path/tmpdir**. Thư mục pytest mặc định `%TEMP%\pytest-of-PC` thuộc `CodexSandboxOffline`; ACL chỉ cho owner, SYSTEM và Administrators. Tài khoản PC trong terminal thường không có quyền cần thiết để pytest liệt kê/tạo thư mục con.
- Đây là xung đột thư mục tạm giữa môi trường agent và người dùng, không phải 134 lỗi model/PR #24. Ca API Teacher không được bật trong lệnh đó nên không phải nguồn của nhóm errors này.
- Hiệu chỉnh hướng dẫn: tạo thư mục temp có GUID mới và truyền `--basetemp` mỗi lần chạy. Không đổi ACL hoặc xóa thư mục tạm cũ. Khiêm đã xác nhận từ terminal: **472 passed, 3 skipped**, không còn 134 errors của thư mục tạm. Failure API Teacher chạy riêng vẫn được ghi nhận là blocker backend.

## Chạy lại trên máy khác

Các lệnh dưới đây dùng đường dẫn tương đối từ thư mục gốc của repository. Cần Python 3.11 trở lên; để so sánh sát với kết quả ghi nhận, dùng Python 3.13.7. `pyproject.toml` khai báo các dependency kiểm thử, gồm `nbformat` và `ipython`.

### Windows PowerShell

```powershell
# Từ thư mục gốc repository
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[api,test]" tldextract==5.4.0 idna==3.20
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs tests\test_api.py
& .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs
# Sau khi backend có model thật và /health.model_ready=true:
& .\.venv\Scripts\python.exe scripts\benchmark_api_latency.py --base-url http://127.0.0.1:8000 --url https://example.com/benchmark --requests 100 --warmup 10 --output reports\tables\week6\api_latency.json
```

### Linux/macOS

```sh
# Từ thư mục gốc repository
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[api,test]' tldextract==5.4.0 idna==3.20
python -m pip check
python -m pytest -p no:cacheprovider -q -rs tests/test_api.py
python -m pytest -p no:cacheprovider -q -rs
# After starting a backend with a real model and /health.model_ready=true:
python scripts/benchmark_api_latency.py --base-url http://127.0.0.1:8000 --url https://example.com/benchmark --requests 100 --warmup 10 --output reports/tables/week6/api_latency.json
```

Các skip do thiếu handoff dữ liệu hoặc không có ca regression vẫn có thể xuất hiện; ghi lại đúng output của môi trường chạy. Để thử backend khi chưa có artifact, không đặt `PHISHGUARD_MODEL_BUNDLE`: theo contract `/health` phải ở trạng thái degraded và `/predict` với URL hợp lệ phải trả 503.
