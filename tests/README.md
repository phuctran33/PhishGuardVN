# Chạy QA — Issue #17

Chạy tại root nhánh `test/api-contract-qa`, đã tích hợp backend PR #22 tại `bbc9eae`. Teacher phát hành nằm ngay trong checkout; không cần cài source từ thư mục PR riêng. Dùng **CPython 3.11**, giữ nguyên `requirements-teacher.txt`, bundle và release lock.

## Cài môi trường mới

Trên Windows, nếu đã cài Python 3.11 qua Python Launcher:

```powershell
py -3.11 -m venv .venv;
& .\.venv\Scripts\python.exe -m pip install -r requirements-teacher.txt -e ".[api,test,teacher]";
& .\.venv\Scripts\python.exe -m pip check
```

Nếu dùng Python portable, thay `py -3.11` bằng đường dẫn Python 3.11 thực tế. Không dùng môi trường Python 3.13 cũ cho Teacher phát hành. Trên macOS/Linux dùng `python3.11 -m venv .venv` và `.venv/bin/python`. README gốc có bước cài `requirements.txt` cho notebook; nghiệm thu API dùng runtime khóa phiên bản và extras trên, không cần chạy lại notebook/train model.

## Full suite và Teacher API bắt buộc

Mỗi lần chạy trên Windows dùng một `--basetemp` mới để tránh thư mục pytest do tài khoản khác tạo. Các lệnh có dấu `;` để paste thành một dòng vẫn đúng.

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-qa-'+[guid]::NewGuid().ToString('N')); & .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" --teacher-root=. --teacher-api -k 'not test_real_external_bundle_matches_saved_scores'
```

Kiểm riêng Teacher integration và công cụ benchmark:

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-teacher-'+[guid]::NewGuid().ToString('N')); & .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" tests\test_teacher_integration.py tests\test_api_benchmark.py --teacher-root=. --teacher-api
```

Kiểm lại API/Teacher, bao gồm bản sửa QA-WIN-01 của Hưng:

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-api-'+[guid]::NewGuid().ToString('N')); & .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" tests\test_api.py tests\test_api_teacher.py --teacher-root=. --teacher-api
```

File `test_api.py` của QA có thêm ca độc lập so với bản 48 test upstream, nên số đếm cuối có thể lớn hơn 48. Xem số thực tế tại `reports/week6_api_qa.md`.

Các suite cũ `test_ablation_ml.py`, `test_readable_ml.py`, `test_brand_features.py`, `test_external_pilot.py` vẫn giữ nguyên. Các lý do skip có thể gặp:

- Bộ tham số brand regression rỗng.
- Thiếu handoff local notebook 02/03; không chạy notebook chỉ để khớp số pass.
- `test_url_research.py` cần extra `research` (Torch/Transformers), không thuộc runtime API; workflow nghiên cứu riêng của Phúc vẫn được giữ.
- Teacher API bị skip nếu quên `--teacher-api`; **không tính skip này là nghiệm thu pass**.

Lệnh QA loại đúng `test_real_external_bundle_matches_saved_scores` để không mở rộng tác vụ sang chấm external. Không tắt assertion hoặc đổi lỗi thành skip. Nếu cần nghiên cứu upstream, xem `docs/week6_phuc_handoff.md` và `week6-benchmark.yml`; không train lại project data để chạy QA.

## Backend thật và latency

Terminal A, tại root checkout:

```powershell
$env:PHISHGUARD_BUNDLE_FORMAT='teacher'; $env:PHISHGUARD_TEACHER_ROOT=(Get-Location).Path; $env:PHISHGUARD_CORS_ORIGINS='http://localhost:3000,http://127.0.0.1:3000'; Remove-Item Env:PHISHGUARD_MODEL_BUNDLE,Env:PHISHGUARD_MODEL_NAME,Env:PHISHGUARD_MODEL_SHA256 -ErrorAction SilentlyContinue; & .\.venv\Scripts\python.exe -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Giữ terminal A chạy. Terminal B:

```powershell
curl.exe -i http://127.0.0.1:8000/health
```

Kỳ vọng HTTP 200, `status=ok`, `model_ready=true`, model `teacher-stacking-v2`, hash/protocol đúng lock. HTTP 200 với `degraded` chỉ chứng minh server hoạt động.

POST bằng JSON file UTF-8 để tránh khác biệt quoting PowerShell/curl:

```powershell
$bodyPath=Join-Path $env:TEMP ('pgvn-request-'+[guid]::NewGuid().ToString('N')+'.json'); [IO.File]::WriteAllText($bodyPath,'{"url":"example.com"}',[Text.UTF8Encoding]::new($false)); curl.exe -i -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' --data-binary "@$bodyPath"
```

Công cụ latency kiểm response, decision rule và threshold, đồng thời lưu cấu hình/artifact. Giữ một process, concurrency 1 và cùng runtime khi đối chiếu số đo:

```powershell
& .\.venv\Scripts\python.exe scripts\benchmark_api_latency.py --help
```

## CI và clean clone

Workflow `tests.yml` chạy **Ubuntu và Windows, CPython 3.11**, cài source của chính checkout, chạy full QA và gate Teacher API riêng. Gate yêu cầu đủ test và không skip; JUnit được tải lên artifacts. Workflow benchmark/research upstream giữ nguyên. CI xanh chỉ áp dụng cho commit đã chạy; thay đổi chưa push chưa có kết quả Actions.

Sau khi tự commit và push, xem Actions đúng SHA vừa push và kiểm cả hai job. Để clone sạch:

```powershell
git clone --branch test/api-contract-qa https://github.com/phuctran33/PhishGuardVN.git PhishGuardVN-clean;
Set-Location .\PhishGuardVN-clean;
git rev-parse HEAD;
py -3.11 -m venv .venv;
& .\.venv\Scripts\python.exe -m pip install -r requirements-teacher.txt -e ".[api,test,teacher]";
& .\.venv\Scripts\python.exe -m pip check
```

Chạy pytest, startup backend, GET health và POST predict bằng các lệnh trên. Không dùng lại venv/handoff dữ liệu/cache model của checkout làm việc. Ghi revision, Python/OS, dependencies, lệnh, exit code, pass/fail/skip và artifact/hash. Bản thử chưa commit phải ghi rõ parents và patch hash, không gọi đó là revision đã phát hành. Xem `reports/tables/week6/clean_clone.json`.

## Web và final E2E

Web thuộc PR #23, checkout riêng chỉ cần cho kiểm UI. Từ `apps/web`, với backend đang chạy:

```powershell
flutter pub get;
flutter analyze;
flutter test;
flutter build web --release --no-web-resources-cdn --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

Dùng Python của venv QA để phục vụ thư mục `build/web` trên port 3000. Kiểm đủ: URL hợp lệ → HTTP 200 và UI đúng response; URL sai port → 422 `invalid_port`; dừng backend thật → UI báo mất kết nối; bật lại → retry thành công cùng trang không reload. Teacher dùng `score >= threshold` từ lock, score meta-LR chưa calibrated, không phải phần trăm an toàn.

Đã có bằng chứng browser thật trên Web `a2bb0dc`, backend `7dfeec5`; commit sửa test `bbc9eae` không đổi source API/model/Web. Kết quả tại `reports/tables/week6/release_e2e.json` và sáu ảnh `reports/figures/week6/khiem_teacher_*.png`. Widget tests dùng HTTP mock; bằng chứng browser dùng Teacher thật. Viewport emulation không phải Android vật lý.

Khi báo lỗi, ghi revision/môi trường/lệnh/expected/actual; ẩn URL riêng tư, token và đường dẫn cá nhân. Tests/security/CI/clean clone hạn 14/11/2026; E2E hậu kiểm trước nghiệm thu 15/11.
