# Kiểm thử local

## Python API và toàn bộ suite

Chạy từ thư mục gốc repository trên PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[api,test]' tldextract==5.4.0 idna==3.20
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs tests\test_api.py
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs tests\test_api_benchmark.py
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs
```

`test_api.py` dùng artifact/estimator tổng hợp cho contract, security guards và parity; đây không phải kết quả của Teacher. `test_api_benchmark.py` kiểm tra công cụ ghi mean/p95 và từ chối benchmark khi `/health.model_ready` là false. Full suite có thể skip test handoff notebook hoặc brand regression khi fixture tương ứng không có; ghi đúng lý do từ output `-rs`.

Khi backend đã sẵn sàng với artifact cần đo, có thể ghi latency HTTP vào JSON:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_api_latency.py --base-url http://127.0.0.1:8000 --url https://example.com/benchmark --requests 100 --warmup 10 --output reports\tables\week6\api_latency.json
```

Chỉ dùng URL tổng hợp, không chứa thông tin riêng tư. Không xem số đo với artifact mock là latency của model thật.

## Flutter Web trên checkout PR #23

Các lệnh sau chạy trong `apps\web` của checkout có PR #23:

```powershell
flutter pub get
flutter analyze
flutter test
```

Widget tests dùng HTTP mock để kiểm tra response, lỗi URL, mất kết nối và retry. Chúng không thay final smoke Web → API → model thật.

## Ghi nhận lỗi

Khi báo lỗi, ghi branch và revision, hệ điều hành/Python, lệnh cài dependencies, lệnh test, số pass/skip/fail cùng lý do, và artifact/model/protocol/hash nếu có. Ghi request/response đã được ẩn dữ liệu nhạy cảm; không đưa raw URL riêng tư, token, secret, traceback có thông tin nhạy cảm hoặc đường dẫn máy cá nhân vào báo cáo.

## Các suite hiện có

- test_splits.py: ID/domain/folds và handoff thật; integration case SKIP nếu chưa tạo handoff.
- test_baseline.py: E1 metrics/leakage/save-load/notes.
- test_readable_ml.py: chạy chính các code cell của notebook v2 trên fixture nhỏ; scaler/search không nhìn outer holdout, validation/test không chọn model, đổi đáp án outer fold không đổi dự đoánfold đó, score SVM margin và CLI Windows/save-load.
- test_experiments.py,test_week5_reporting.py: giữ kiểm chứng tuyến v1 nâng cao đã lưu; không phải nội dung cần đọc trước notebook v2.

Kết quả lịch sử ngày 04/11/2026: **152 passed**, không skip; `pip check` pass. Đã tích hợp parser/brand từ Hy PR #5.

## Clean clone

Các lệnh này kiểm tra revision đang có trên remote branch; chúng không đưa các thay đổi chưa commit từ working tree vào clone:

```powershell
Set-Location $env:TEMP
git clone --branch test/api-contract-qa https://github.com/phuctran33/PhishGuardVN.git PhishGuardVN-clean
Set-Location .\PhishGuardVN-clean
git rev-parse HEAD
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[api,test]' tldextract==5.4.0 idna==3.20
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs
.\.venv\Scripts\python.exe -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Trong terminal khác, kiểm tra backend bằng `curl.exe -i http://127.0.0.1:8000/health`. Không cấu hình model thì `degraded/not_configured` là kết quả có chủ đích; URL hợp lệ gửi tới `/predict` phải trả 503. Ghi SHA, Python/OS, các lệnh, output pytest/health và artifact hoặc cấu hình còn thiếu. Clean clone của thay đổi QA mới chỉ có thể xác nhận sau khi revision đó được commit/push.

- `test_brand_features.py`: hợp đồng/parser/brand của Hy.
- `test_ablation_ml.py`: chạy code cells notebook E2 ablation; E1/E2 cùng ID/folds, scaler/tuning trong fitting partition, không dùng nhãn Val/Test chọn model, đổi outer answers không đổi dự đoán fold đó; invalid pairing/lexical/schema/Test dừng trước fit; E2 reload/direct-extraction parity và reference snapshot/source drift.

Tests bảo vệ tính đúng code/giao thức, không chứng minh chất lượng ngoài dataset. Xem reports/week5_readable.md để đọc kết quả/giới hạn.
