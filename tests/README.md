# Chạy QA — tuần 7 (#31) và bộ kiểm thử tuần 6 (#17)

Ma trận bổ sung cho tuần 7 nằm tại [`reports/week7_test_matrix.md`](../reports/week7_test_matrix.md). Các fixture URL và lệnh pytest bên dưới là nền tuần 6 được tái sử dụng; không thay thế các ca QR, X-Ray hay Android mới trong ma trận.

Phần Web của Hưng và Student Python/artifact của Phúc đã có kết quả để bàn giao; xem [bảng chốt phạm vi](../reports/week7_qa.md#chốt-phạm-vi-bàn-giao-hưng-và-phúc). K7.4 chưa bao gồm Student Python–Dart parity; K7.5 còn Actions sau khi tự push và Android offline smoke. Bản bàn giao Android mới của Hy chưa được kiểm riêng trong đợt này. Không dùng trạng thái đã approve Web để đánh dấu hoàn thành các bước Android.

## QA Web tuần 7 — bàn giao của Hưng

Kết quả độc lập và lịch sử lỗi: [`reports/week7_qa.md`](../reports/week7_qa.md). Source mới nhất đã kiểm là commit sửa focus `5f112fc597339ea213eff3f07c745629cc18d8fc` ở checkout riêng `PhishGuardVN-w7-hung-review`. Các lệnh dưới đây bắt đầu tại root repo QA; dùng dấu `;` khi paste thành một dòng. Source tuần 7 chưa được merge vào checkout QA này.

Nếu chưa có checkout bàn giao, tạo một lần:

```powershell
git clone --branch feat/w7-hung-web-analysis https://github.com/phuctran33/PhishGuardVN.git ..\PhishGuardVN-w7-hung-review; git -C ..\PhishGuardVN-w7-hung-review checkout --detach 5f112fc597339ea213eff3f07c745629cc18d8fc
```

Tạo venv riêng trong checkout bàn giao bằng CPython 3.11; nếu dùng portable Python, thay `py -3.11` bằng executable đã cài:

```powershell
py -3.11 -m venv ..\PhishGuardVN-w7-hung-review\.venv; & ..\PhishGuardVN-w7-hung-review\.venv\Scripts\python.exe -m pip install -r ..\PhishGuardVN-w7-hung-review\requirements-teacher.txt -e '..\PhishGuardVN-w7-hung-review[api,test,teacher]'; & ..\PhishGuardVN-w7-hung-review\.venv\Scripts\python.exe -m pip check
```

**25 test QA bổ sung** kiểm `/inspect`, lỗi request/adapter, CORS, không truy cập mạng/không log raw URL, domain giả qua userinfo/query, E2/reference và việc inspection không đổi prediction Teacher thật. Truyền file `inspection_qa.py` trực tiếp để dùng source tuần 7 trong venv bàn giao:

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-w7-own-'+[guid]::NewGuid().ToString('N')); & ..\PhishGuardVN-w7-hung-review\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" tests\week7\inspection_qa.py --teacher-root=..\PhishGuardVN-w7-hung-review
```

Kiểm lại **73 test upstream** tại checkout bàn giao:

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-w7-focused-'+[guid]::NewGuid().ToString('N')); & ..\PhishGuardVN-w7-hung-review\.venv\Scripts\python.exe -m pytest -c ..\PhishGuardVN-w7-hung-review\pyproject.toml -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" ..\PhishGuardVN-w7-hung-review\tests\test_url_inspection.py ..\PhishGuardVN-w7-hung-review\tests\test_api.py ..\PhishGuardVN-w7-hung-review\tests\test_api_teacher.py
```

Full regression phải chạy từ root checkout bàn giao vì một số test dùng đường dẫn tương đối. Mở terminal khác tại đó:

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-w7-full-'+[guid]::NewGuid().ToString('N')); & .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" --teacher-root=. --teacher-api -k 'not test_real_external_bundle_matches_saved_scores'
```

Venv `api,test,teacher` đã kiểm: **612 passed, 3 skipped, 1 deselected**. Ngoài hai skip lịch sử, có skip module research vì thiếu extra `research`; 27 test research đã được chạy riêng trong môi trường research có sẵn. Muốn kiểm cả module này, cài thêm `-r requirements-teacher.txt -e '.[api,test,teacher,research]'` trong checkout bàn giao; không cần extra research để nghiệm thu Web/QR/inspection.

Kiểm Flutter từ `PhishGuardVN-w7-hung-review/apps/web`:

```powershell
flutter pub get; flutter analyze --no-pub; flutter test --no-pub; flutter build web --release --no-pub --no-web-resources-cdn --dart-define=API_BASE_URL=http://127.0.0.1:18767
```

Flutter Web sau sửa có **48 tests passed**, analyze sạch và release build đạt. **Browser smoke tự động** dùng Node.js và Playwright 1.65.0. Cài dependencies và Chromium tại repo QA; có thể thay `npm`/`node` bằng đường dẫn executable khi PATH chưa nhận:

```powershell
npm --prefix tests/week7 ci; Push-Location tests/week7; npx playwright install chromium; Pop-Location
```

Release build bên trên phải trỏ API port 18767. Runner tự bật/tắt Uvicorn port 18767 và Web server port 13007; hai port phải đang trống. Không cần tự bật backend trước. Truyền Chromium được Playwright cài để dùng cùng loại browser với CI:

```powershell
$qaChrome=node -p "require('./tests/week7/node_modules/playwright').chromium.executablePath()"; node tests/week7/web_smoke.cjs --handoff-root=../PhishGuardVN-w7-hung-review "--chrome=$qaChrome" --output=reports/tables/week7/web_browser_fixed.json
```

Kiểm lại riêng ca focus sau ảnh QR hỏng:

```powershell
$qaChrome=node -p "require('./tests/week7/node_modules/playwright').chromium.executablePath()"; node tests/week7/web_smoke.cjs --handoff-root=../PhishGuardVN-w7-hung-review --scenario=qr-focus "--chrome=$qaChrome" --output=reports/tables/week7/qr_focus_fixed.json
```

Trên `5f112fc`, full browser smoke **20 pass, 0 fail**, repro riêng **1 pass**, exit code 0; lỗi QA-W7-WEB-01 đã khắc phục. Các file `web_browser_qa.json`/`qr_focus_qa.json` cũ giữ bằng chứng fail trên `701b8f5`. Runner dùng HTTP/Teacher thật; timeout được kiểm có kiểm soát trong Flutter unit tests upstream. Không quy kết kết quả browser/viewport thành Android device test.

Gate Teacher API của QA tuần 6 được dùng lại trên source mới (**15 passed**, 17 test khác bị deselect bởi `-m teacher_api`):

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-w7-teacher-'+[guid]::NewGuid().ToString('N')); & ..\PhishGuardVN-w7-hung-review\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" tests\test_teacher_integration.py --teacher-root=..\PhishGuardVN-w7-hung-review --teacher-api -m teacher_api
```

Dart package hiện có đạt **294 tests**. Chạy từ root checkout Hưng (không phải repo QA):

```powershell
Push-Location mobile/packages/phishguard_features; dart pub get; dart test --reporter expanded; Pop-Location
```

Flutter app nền đạt analyze sạch và **3 widget tests**. Trước khi chạy, đồng bộ bốn assets cố định theo README app; PowerShell dưới đây tương đương phần chép assets của `mobile/tool/sync_assets.sh`, không cần `shasum` trên Windows:

```powershell
$qaAssets='mobile/app/assets'; New-Item -ItemType Directory -Force $qaAssets | Out-Null; $qaSources=@('src/phishguard_vn/resources/brand_reference_v1.csv','mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt','docs/mobile_parity_cases.json','docs/mobile_parity_cases_extra.json'); foreach ($qaSource in $qaSources) { $qaCopy=Join-Path $qaAssets (Split-Path $qaSource -Leaf); Copy-Item -LiteralPath $qaSource -Destination $qaCopy; if ((Get-FileHash $qaSource).Hash -ne (Get-FileHash $qaCopy).Hash) { throw "Asset mismatch: $qaSource" } }; Push-Location mobile/app; flutter pub get --enforce-lockfile; flutter analyze --no-pub; flutter test --no-pub; Pop-Location
```

Đây là regression của package/app nền có trong snapshot Hưng; không nhận đó là nghiệm thu bàn giao Android tuần 7 hoặc smoke Teacher trên thiết bị tắt mạng.

### CI Web tuần 7

Workflow [`week7-web.yml`](../.github/workflows/week7-web.yml) có tên **Week 7 QA**, chạy khi push/PR và hỗ trợ chạy thủ công. Hai job **Flutter Web / ubuntu-latest** và **Flutter Web / windows-latest** dùng Flutter 3.47.9, Python 3.11, Node.js 24 và Playwright theo npm lockfile. Mỗi job chạy:

1. `flutter pub get --enforce-lockfile`, analyze, unit/widget tests và release build không CDN.
2. API/inspection/Teacher tests upstream, full regression và hai gate QA có sẵn (`inspection_qa.py`, Teacher API acceptance), trên cùng source Web đã chọn. Cài đủ `api,test,teacher` extras để full regression không thiếu LightGBM/notebook dependencies.
3. `dart test` của package và analyze/widget tests của app nền; đồng bộ assets từ nguồn chuẩn và giữ lockfile app.
4. Chromium thật → API → Teacher bằng `web_smoke.cjs`. Browser dùng Chromium do Playwright cài, không phụ thuộc Chrome cài sẵn trên runner.

SHA source được chọn theo thứ tự: input thủ công `web_sha` (đủ 40 ký tự), SHA checkout QA nếu đồng thời có `apps/web/test/week7_test.dart` và `src/phishguard_vn/url_inspection.py`, hoặc giá trị **`WEB_HANDOFF_SHA`** trong workflow. Hiện fallback là `5f112fc597339ea213eff3f07c745629cc18d8fc`. Chỉ có Web tuần 6 từ `main` không đủ để chọn source QA làm source tuần 7. Source được checkout riêng vào `web-source`; SHA QA/Web được ghi trong Job summary và `source.txt`. Workflow không tự chạy theo đầu branch đang thay đổi.

Hai job **Student Python / Ubuntu và Windows** checkout riêng Phúc tại `STUDENT_HANDOFF_SHA=1cad94c88195ebea6e4737bbfc863cbe4b2ff384` (hoặc input `student_sha` đủ 40 ký tự), cài Python 3.11/runtime khóa phiên bản/LightGBM 4.7.0 rồi chạy 43 + 3 + 29 tests K7.4 đã có. Gate kiểm JUnit đủ số ca và không skip; không chạy project training hay đổi engine sang Student.

Sau khi bạn tự commit/push, mở **Actions → Week 7 QA**, đối chiếu đúng commit và kiểm đủ **4 job**: Web hai OS, Student hai OS. Tải artifacts `week7-web-<OS>`/`week7-student-<OS>` để xem SHA nguồn, versions, logs, JSON/JUnit và ảnh browser. Job Web giữ ca focus như regression bắt buộc; không dùng `continue-on-error` hoặc skip để làm xanh CI. Các gate trọng tâm Web/Dart/Flutter/Teacher yêu cầu không skip; full regression ghi riêng các skip lịch sử. **Workflow mới chưa có kết quả Actions khi chưa commit/push.** Android network-disabled Teacher smoke và Student Python–Dart parity vẫn cần bàn giao/build tương ứng của Hy.

## K7.4 — Student LightGBM của Phúc

Source đã kiểm: `1cad94c88195ebea6e4737bbfc863cbe4b2ff384`, branch `phuc-week7-student`, ở checkout riêng `PhishGuardVN-w7-student-review`. Không chép đè Student/Teacher vào repo QA hoặc checkout Web. Kết quả: **43 test QA độc lập**, **3 test LightGBM upstream** và **29 test Student cũ** đạt trong ba lần chạy riêng; không fail/skip. Xem [báo cáo](../reports/week7_qa.md#k74--kiểm-student-lightgbm-ngày-18112026) và [JSON bằng chứng](../reports/tables/week7/student_verification.json).

Các lệnh sau bắt đầu tại root repo QA. Nếu đã có checkout/venv do QA tạo thì bỏ qua hai bước tạo và cài môi trường.

Tạo checkout bàn giao một lần, cố định đúng revision:

```powershell
git clone --branch phuc-week7-student https://github.com/phuctran33/PhishGuardVN.git ..\PhishGuardVN-w7-student-review; git -C ..\PhishGuardVN-w7-student-review checkout --detach 1cad94c88195ebea6e4737bbfc863cbe4b2ff384
```

Cần **CPython 3.11**; QA thực tế dùng 3.11.14 x64 trên Windows. Tạo venv riêng và cài đúng runtime cùng LightGBM 4.7.0. Nếu máy chưa có `py -3.11`, cài Python 3.11 hoặc dùng đường dẫn interpreter 3.11 sẵn có thay cho `py -3.11`; không dùng Python 3.13/3.15 cho frozen E2.

```powershell
py -3.11 -m venv ..\PhishGuardVN-w7-student-review\.venv; & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe -m pip install -r ..\PhishGuardVN-w7-student-review\requirements-teacher.txt -e '../PhishGuardVN-w7-student-review[test]' lightgbm==4.7.0
```

Kiểm source/runtime và dependencies:

```powershell
git -C ..\PhishGuardVN-w7-student-review rev-parse HEAD; & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe --version; & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe -m pip check
```

Chạy bộ QA bổ sung (**43 passed**). File đặt tên `student_qa.py` để chỉ chạy khi được chỉ định, tránh collect bằng source tuần 6 chưa có Student. Bộ test lấy root từ module Student đã cài editable; thiếu artifact hoặc sai runtime là fail, không tự skip.

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:OMP_NUM_THREADS='1'; $qaTemp=Join-Path $env:TEMP ('pgvn-student-qa-'+[guid]::NewGuid().ToString('N')); & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" tests\week7\student_qa.py
```

Chạy đúng test được Phúc bàn giao (**3 passed**, hai cảnh báo Pandas về `float_precision`), gồm đối chiếu output Validation đã lưu, không chọn lại model/ngưỡng:

```powershell
$env:OMP_NUM_THREADS='1'; $qaTemp=Join-Path $env:TEMP ('pgvn-student-upstream-'+[guid]::NewGuid().ToString('N')); & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" ..\PhishGuardVN-w7-student-review\tests\test_student_lightgbm.py
```

Giữ các kiểm thử Student cũ (**29 passed**, ba cảnh báo Pandas cùng loại):

```powershell
$qaTemp=Join-Path $env:TEMP ('pgvn-student-old-'+[guid]::NewGuid().ToString('N')); & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$qaTemp" ..\PhishGuardVN-w7-student-review\tests\test_student.py ..\PhishGuardVN-w7-student-review\tests\test_student_comparison.py
```

Chạy CLI thử hai mode, mỗi lệnh trả năm dòng JSON:

```powershell
& ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe ..\PhishGuardVN-w7-student-review\scripts\predict_lightgbm_student.py --examples
```

```powershell
& ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe ..\PhishGuardVN-w7-student-review\scripts\predict_lightgbm_student.py --mode hard_only --examples
```

Mode mặc định của **Student CLI** là `kd_mixed`; engine chính của ứng dụng vẫn là Teacher stacking v2. Student là `experimental`, score `uncalibrated_sigmoid`, quyết định `score >= threshold`: KD `0.6204500086017339`, hard `0.6157178977907972`. Không hiển thị score thành phần trăm an toàn.

52 fixture hợp lệ và 6 fixture bị từ chối được kiểm ở từng mode; Python–native LightGBM–JSON khớp ở `atol=1e-12`. Đây **chưa phải Python–Dart hoặc Android parity**. Chưa nhận adapter/build Student của Hy trong đợt này nên chưa tick toàn bộ K7.4. Các targets/manifest và record lịch sử đủ để kiểm lineage mà không cần load cache Teacher; QA không nhận đã kiểm lại bytes của cache lịch sử không được đưa vào Git. Không train lại Teacher/Student trên dữ liệu dự án, không chạy lại benchmark, Official Test hoặc external. K7.5/Web và CI được hướng dẫn riêng ở phần trên.

## QA tuần 6 — bộ kiểm thử nền

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
