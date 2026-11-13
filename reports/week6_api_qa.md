# Báo cáo QA API — Issue #17

## Phạm vi và môi trường

- Nhánh kiểm tra: `test/api-contract-qa`, dựa trên nhánh backend PR #22.
- Lần chạy ghi nhận: 10/11/2026.
- Hệ điều hành: Windows, chạy bằng PowerShell.
- Python: 3.13.7.
- Gói được cài từ `pyproject.toml` với extra `api,test`; `tldextract` 5.4.0 và `idna` 3.20.
- Test API dùng estimator và artifact tổng hợp trong thư mục tạm; không dùng model thật.
- Artifact `week5_e2_ablation.joblib` không có trong checkout này. Không đặt biến môi trường model theo đường dẫn ví dụ.

## Kết quả

- `tests/test_api.py`: **43 passed** trong lần chạy lại working tree ngày 13/11/2026.
- `tests/test_api_benchmark.py`: **2 passed**.
- Toàn bộ pytest suite: **439 passed, 2 skipped** trong lần chạy lại ngày 13/11/2026 trên Python 3.13.7.
- `pip check`: không có dependency lỗi.
- `git diff --check`: không có lỗi whitespace.

Hai test bị skip:

- `tests/test_brand_regressions.py:58`: fixture không sinh ra bộ tham số brand regression.
- `tests/test_splits.py:210`: chưa có handoff dữ liệu local từ notebook 02 và 03.

Các số **419/2** bạn chạy trước đó và **420/1** trong báo cáo PR #22 thuộc revision/môi trường khác; test API của nhánh QA cũng đã được bổ sung từ 33 lên 43 ca. Vì vậy cần ghi kèm revision, môi trường và handoff khi so sánh; số mới nhất của working tree QA là **439/2**.

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
- Kết quả mới ở trên nằm trong working tree chưa commit. GitHub Actions xanh hiện chỉ chứng minh commit `2a3efeb` và lần đồng bộ PR #25; cần push commit mới để CI chạy đúng phiên bản này.
- Clean clone được ghi nhận trước đó tại SHA `2a3efebcc9cc4c6c21a65511a8c7498d6bc0dc69`, không có artifact model. Nó chưa kiểm tra các thay đổi working tree hiện tại; clean clone cho revision mới cần thực hiện sau khi các thay đổi được commit/push.

## Trạng thái còn lại

- Workflow CI đã được thêm và đã pass cho commit `2a3efeb`; các thay đổi QA hiện tại chưa có CI run vì chưa commit/push.
- Clean-clone đã pass cho SHA `2a3efeb` trong cấu hình không model, với health degraded và prediction 503 đúng contract. Chưa có clean-clone chạy trên các thay đổi working tree mới.
- API–CLI parity hiện đã kiểm tra với artifact tổng hợp; parity model thật vẫn chờ artifact tương thích.
- Latency mean/p95 đã có baseline tổng hợp; benchmark với model thật còn chờ artifact.
- Smoke Web → API với model giả đã cho kết quả hợp lệ; final smoke Flutter → API → model thật vẫn là hậu kiểm sau bàn giao ổn định PR #19 và Teacher/artifact tương thích.

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
