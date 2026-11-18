# Chạy QA — tuần 7 (#31) và bộ kiểm thử tuần 6 (#17)

Ma trận bổ sung cho tuần 7 nằm tại [`reports/week7_test_matrix.md`](../reports/week7_test_matrix.md). Các fixture URL và lệnh pytest bên dưới là nền tuần 6 được tái sử dụng; không thay thế các ca QR, X-Ray hay Android mới trong ma trận.

Phần Web của Hưng và Student Python/artifact của Phúc đã có kết quả để bàn giao; xem [bảng chốt phạm vi](../reports/week7_qa.md#chốt-phạm-vi-bàn-giao-hưng-và-phúc). Teacher và Student đã được đối chiếu Python–Dart trên laptop. Student đã có thêm parity/offline/performance trên Android emulator qua app QA riêng; Teacher Android runtime K7.3 và Actions cho thay đổi mới vẫn theo dõi riêng. Không dùng kết quả Student để tick Teacher hoặc điện thoại vật lý.

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

Workflow [`week7-web.yml`](../.github/workflows/week7-web.yml) có tên **Week 7 QA**, chạy khi push/PR và hỗ trợ chạy thủ công. Hai job **Web and Android host / ubuntu-latest** và **Web and Android host / windows-latest** dùng Flutter 3.47.9 và Python 3.11. Các bước 1–3 chạy trên cả hai hệ điều hành; bước 4 chỉ chạy trên Windows, dùng Node.js 24 và Playwright theo npm lockfile:

1. `flutter pub get --enforce-lockfile`, analyze, unit/widget tests và release build không CDN.
2. API/inspection/Teacher tests upstream, full regression và hai gate QA có sẵn (`inspection_qa.py`, Teacher API acceptance), trên cùng source Web đã chọn. Cài đủ `api,test,teacher` extras để full regression không thiếu LightGBM/notebook dependencies.
3. Checkout riêng bản Hy qua `ANDROID_HANDOFF_SHA=a4d7b0e8e7d7845368bb3061c8e754c7cbe1224e` (hoặc input `android_sha` đủ 40 ký tự), chạy 294 Dart tests, analyze/46 Flutter tests và 5 QA host tests dùng output Python mới. Đồng bộ đủ bảy assets từ nguồn chuẩn, giữ lockfile app; không tính host tests là Android device smoke.
4. **Chỉ Windows:** Chromium thật → API → Teacher bằng `web_smoke.cjs`. Browser dùng Chromium do Playwright cài, không phụ thuộc Chrome cài sẵn trên runner. Giữ đủ 20 ca, gồm thay URL sau lỗi QR và kiểm focus; không dùng retry hoặc bỏ assertion để đổi kết quả lỗi thành pass.

Issue #31 yêu cầu CI phù hợp và bằng chứng Web E2E, không bắt buộc browser smoke trên cả Windows lẫn Ubuntu. Phạm vi browser hiện tại là Windows; Ubuntu tiếp tục chạy regression API/Teacher/Dart/Flutter trên host. Browser Ubuntu chưa được nghiệm thu trong cấu hình này. Lượt lỗi trên Ubuntu tại `8943bbe` và lý do thu gọn phạm vi được ghi trong [`week7_qa.md`](../reports/week7_qa.md#phạm-vi-browser-ci-sau-lượt-chạy-8943bbe).

SHA source được chọn theo thứ tự: input thủ công `web_sha` (đủ 40 ký tự), SHA checkout QA nếu đồng thời có `apps/web/test/week7_test.dart` và `src/phishguard_vn/url_inspection.py`, hoặc giá trị **`WEB_HANDOFF_SHA`** trong workflow. Hiện fallback là `5f112fc597339ea213eff3f07c745629cc18d8fc`. Chỉ có Web tuần 6 từ `main` không đủ để chọn source QA làm source tuần 7. Source được checkout riêng vào `web-source`; SHA QA/Web được ghi trong Job summary và `source.txt`. Workflow không tự chạy theo đầu branch đang thay đổi.

Hai job **Student Python and Dart / Ubuntu và Windows** checkout riêng Phúc tại `STUDENT_HANDOFF_SHA=1cad94c88195ebea6e4737bbfc863cbe4b2ff384`, cài Python 3.11/runtime khóa phiên bản/LightGBM 4.7.0 rồi chạy 43 + 3 + 29 tests K7.4 đã có. Có thêm adapter QA riêng: 44 Flutter tests, hai mode parity và 2 tests assets/UI của app QA sinh ra. Gate kiểm đủ số ca và không skip; không chạy project training hay đổi engine sang Student. Lock QA đang ghim artifact/revision này; input revision khác phải được review cùng lock trước khi chạy, không tự chấp nhận bundle mới.

Sau khi bạn tự commit/push, mở **Actions → Week 7 QA**, đối chiếu đúng commit và kiểm đủ **4 job**: Web/Android host hai OS, Student hai OS. Tải artifacts `week7-web-<OS>`/`week7-student-<OS>` để xem SHA nguồn, versions, logs, JSON/JUnit và ảnh browser. Job Web giữ ca focus như regression bắt buộc; không dùng `continue-on-error` hoặc skip để làm xanh CI. Các gate trọng tâm Web/Dart/Flutter/Teacher yêu cầu không skip; full regression ghi riêng các skip lịch sử. CI bản `3bfd45a` đã đạt 6/6; thay đổi thêm gate Hy chỉ có kết quả Actions sau khi tự commit/push. Android network-disabled Teacher smoke và Student Python–Dart parity không được tính là pass từ các gate host.

## K7.3 — kiểm Teacher Android của Hy

Snapshot host ban đầu: `a4d7b0e8e7d7845368bb3061c8e754c7cbe1224e`; lượt host/Android hiện tại: `94abdbf9d9fd1be6452284d2a84f26ec937f2474`, branch `feat/w7-android-teacher-integration`. Commit mới chỉ thêm tài liệu; mã app Teacher không đổi. Kết quả tại [báo cáo QA](../reports/week7_qa.md#k73--teacher-android-runtime-và-release-offline), [JSON nghiệm thu](../reports/tables/week7/android_verification.json), [parity host](../reports/tables/week7/android_host_parity.json) và [Android runtime](../reports/tables/week7/teacher_android_runtime.json). Python chạy mới bằng released loader; không train lại, không dùng output giả.

Nếu chưa có checkout, tạo một lần từ root QA:

```powershell
git clone --branch feat/w7-android-teacher-integration https://github.com/phuctran33/PhishGuardVN.git ..\PhishGuardVN-w7-hy-review; git -C ..\PhishGuardVN-w7-hy-review checkout --detach 94abdbf9d9fd1be6452284d2a84f26ec937f2474
```

Cần CPython 3.11, Flutter 3.47.9/Dart 3.13.7. Máy QA đã có venv trong checkout Hy; người chạy mới tạo bằng interpreter 3.11 (dùng executable portable nếu `py -3.11` chưa được đăng ký):

```powershell
py -3.11 -m venv ..\PhishGuardVN-w7-hy-review\.venv; & ..\PhishGuardVN-w7-hy-review\.venv\Scripts\python.exe -m pip install -r ..\PhishGuardVN-w7-hy-review\requirements-teacher.txt -e '../PhishGuardVN-w7-hy-review[test]'; & ..\PhishGuardVN-w7-hy-review\.venv\Scripts\python.exe -m pip check
```

Từ root checkout Hy, đồng bộ bảy assets. Lệnh tương đương phần chép của `mobile/tool/sync_assets.sh`, dùng được trên Windows và không sửa assets gốc:

```powershell
$qaAssets='mobile/app/assets'; New-Item -ItemType Directory -Force $qaAssets | Out-Null; $qaSources=@('src/phishguard_vn/resources/brand_reference_v1.csv','mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt','docs/mobile_parity_cases.json','docs/mobile_parity_cases_extra.json','artifacts/teacher_v2_android/dart_svm_model.json','artifacts/teacher_v2_android/dart_teacher_v2_model.json','artifacts/teacher_v2_android/manifest.json'); foreach ($qaSource in $qaSources) { $qaName=if ($qaSource -eq 'artifacts/teacher_v2_android/manifest.json') { 'teacher_v2_manifest.json' } else { Split-Path $qaSource -Leaf }; $qaCopy=Join-Path $qaAssets $qaName; Copy-Item -LiteralPath $qaSource -Destination $qaCopy; if ((Get-FileHash $qaSource).Hash -ne (Get-FileHash $qaCopy).Hash) { throw "Asset mismatch: $qaSource" } }
```

Cũng từ root Hy: app analyze sạch và **46 tests passed**; package **294 tests passed**:

```powershell
Push-Location mobile/app; flutter pub get --enforce-lockfile; flutter analyze --no-pub; flutter test --no-pub; Pop-Location; Push-Location mobile/packages/phishguard_features; dart pub get; dart test; Pop-Location
```

Quay lại root **repo QA**, tạo output Python mới và sinh test Flutter vào `.dart_tool` của Hy (thư mục bị ignore). Nguồn test là `android_teacher_qa_test.dart.in`; không đặt file `.dart` độc lập ngoài Flutter package để VS Code phân tích nhầm dependency. File được sinh giống nguyên bytes nguồn, vẫn phải compile và qua analyzer trong đúng package.

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:OMP_NUM_THREADS='1'; & ..\PhishGuardVN-w7-hy-review\.venv\Scripts\python.exe tests\week7\android_reference.py --android-root=..\PhishGuardVN-w7-hy-review --output=reports/tables/week7/android_python_reference.json
```

Kỳ vọng **47 classified, 9 rejected**. Chạy kiểm độc lập trong Flutter host — **5 tests passed**, analyzer không issue:

```powershell
$qaRoot=(Get-Location).Path; $hyRoot=(Resolve-Path ..\PhishGuardVN-w7-hy-review).Path; $qaRef=Join-Path $qaRoot 'reports/tables/week7/android_python_reference.json'; $qaOut=Join-Path $qaRoot 'reports/tables/week7/android_host_parity.json'; Push-Location "$hyRoot/mobile/app"; flutter analyze --no-pub .dart_tool/week7_teacher_qa_test.dart; flutter test --no-pub .dart_tool/week7_teacher_qa_test.dart "--dart-define=QA_ANDROID_REFERENCE=$qaRef" "--dart-define=QA_ANDROID_OUTPUT=$qaOut" --reporter expanded; Pop-Location
```

Các test dùng loader/classifier thật, đối chiếu score/label/version/threshold/rule/feature order, thử thiếu model và sai threshold, chặn HTTP trên host. Max score delta ghi nhận `8.881784197001252e-16`, nhỏ hơn `atol=1e-6`. Python bị chặn DNS/socket khi tạo reference. Đây là **host parity và fault injection**, không phải Android chạy khi tắt mạng.

### Teacher Android runtime và APK release

Đã kiểm riêng Teacher trên Android 17/API 37/x86_64 emulator; không suy ra từ kết quả Student. Cần Android SDK, emulator đã boot, API 36 và NDK 28.2.13676358 theo cấu hình Flutter 3.47.9. `flutter doctor -v` phải nhận toolchain; dùng `flutter emulators`/`flutter devices` để chọn ID. Các lệnh bên dưới dùng `emulator-5554`, thay bằng ID thực tế nếu khác. Flutter phải có trong PATH; nếu chưa có, truyền `--flutter=đường_dẫn_flutter.bat` cho controller.

Sau khi đồng bộ assets và tạo reference Python ở trên, từ root QA tạo bản integration riêng dưới thư mục ignored. Mã `lib/` và Android build của Hy được chép nguyên bytes, kèm hashes; chỉ thêm dependency `integration_test`, reference QA và entrypoint kiểm thử. Không sửa checkout Hy:

```powershell
& ..\PhishGuardVN-w7-hy-review\.venv\Scripts\python.exe tests/week7/prepare_teacher_runtime.py --android-root=../PhishGuardVN-w7-hy-review; Push-Location tests/week7/.teacher_android_harness; flutter pub get; flutter analyze --no-pub integration_test/teacher_runtime_test.dart test_driver/teacher_driver.dart; Pop-Location
```

Chạy integration trên emulator. Controller chỉ chấp nhận emulator, xác nhận airplane on/Wi-Fi off/data off và không có default route IPv4/IPv6; khôi phục đúng trạng thái mạng ban đầu trong `finally`, kể cả khi test lỗi:

```powershell
$qaSdk=Join-Path $env:LOCALAPPDATA 'Android/sdk'; & ..\PhishGuardVN-w7-hy-review\.venv\Scripts\python.exe tests/week7/run_teacher_android.py --android-root=../PhishGuardVN-w7-hy-review "--adb=$qaSdk/platform-tools/adb.exe" --device=emulator-5554 --phase=integration --output=reports/tables/week7/teacher_android_runtime.json
```

Kỳ vọng **3 nhóm kiểm ứng dụng đạt**: 47 classified/9 rejected khớp Python và metadata/hashes; missing/corrupt model/sai threshold cùng màn hình lỗi/retry; UI benign/phishing/invalid port. Flutter còn in các ca thiết lập/teardown của framework; không cộng thành 5 ca nghiệp vụ. UI integration kiểm soát keyboard transport của Flutter; không nhận là kiểm native IME.

Build APK release nguyên bản của Hy, không dùng entrypoint integration:

```powershell
Push-Location ../PhishGuardVN-w7-hy-review/mobile/app; flutter build apk --release --target-platform android-x64; Pop-Location
```

Cài lại chính APK release đó, force-stop/mở lại ba lần khi Android tắt mạng, chạm URL mẫu bằng ADB và kiểm nhãn/model/threshold thật; lưu JSON và ảnh:

```powershell
$qaSdk=Join-Path $env:LOCALAPPDATA 'Android/sdk'; & ..\PhishGuardVN-w7-hy-review\.venv\Scripts\python.exe tests/week7/run_teacher_android.py --android-root=../PhishGuardVN-w7-hy-review "--adb=$qaSdk/platform-tools/adb.exe" --device=emulator-5554 --phase=release --output=reports/tables/week7/teacher_android_release.json --screenshot=reports/figures/week7/teacher_android_release_offline.png
```

Lượt thực tế đạt cả integration và release; mạng được khôi phục sau mỗi lượt. Bằng chứng: [runtime](../reports/tables/week7/teacher_android_runtime.json), [release](../reports/tables/week7/teacher_android_release.json), [ảnh offline](../reports/figures/week7/teacher_android_release_offline.png). Kết quả chỉ xác minh emulator x86_64; không nhận điện thoại vật lý/ARM64, mọi IME hoặc browser Linux đã được kiểm. Teacher app vẫn mặc định; không thêm Student vào sản phẩm Hy.

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

52 fixture hợp lệ và 6 fixture bị từ chối được kiểm ở từng mode; Python–native LightGBM–JSON khớp ở `atol=1e-12`. Đây là kết quả Python trước khi bổ sung adapter Dart, không phải Android parity. Các targets/manifest và record lịch sử đủ để kiểm lineage mà không cần load cache Teacher; QA không nhận đã kiểm lại bytes của cache lịch sử không được đưa vào Git. Không train lại Teacher/Student trên dữ liệu dự án, không chạy lại benchmark, Official Test hoặc external. Kết quả Student Dart mới nằm ngay bên dưới.

## Student Android — triển khai QA theo hướng dẫn Hy `94abdbf`

Hướng dẫn gốc: [`week7_student_android_handover.md`](https://github.com/phuctran33/PhishGuardVN/blob/94abdbf9d9fd1be6452284d2a84f26ec937f2474/docs/week7_student_android_handover.md). Commit này chỉ thêm tài liệu. Adapter nằm tại `tests/week7/student_android/lib/`, dùng lại package `mobile/packages/phishguard_features` hiện có; không sửa source/app của Hy hoặc thay engine Teacher. Đây là adapter thử nghiệm phục vụ QA, chưa phải Student được tích hợp vào sản phẩm Android của Hy.

Điều kiện: Flutter **3.47.9 / Dart 3.13.7**, Python **3.11** với môi trường Student đã cài ở mục trên; checkout Phúc đúng `1cad94c88195ebea6e4737bbfc863cbe4b2ff384`. Manifest, bytes/kích thước của bảy file được ghim trong `student_lock.json`; không chép model vào Git lần nữa. Helper chỉ chép assets vào thư mục ignored của package QA, chạy Python inference offline và tạo reference mới. Teacher/E2/reference giữ nguyên.

Tại root QA, chạy từng dòng (mỗi dòng độc lập, dán một dòng được):

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:OMP_NUM_THREADS='1'; & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe tests\week7\prepare_student_android.py --student-root=..\PhishGuardVN-w7-student-review --output=reports/tables/week7/student_android_python_reference.json
```

```powershell
$qaRoot=(Get-Location).Path; $qaOutput=Join-Path $qaRoot 'reports/tables/week7/student_dart_parity.json'; Push-Location tests\week7\student_android; flutter pub get --enforce-lockfile; flutter analyze --no-pub; flutter test --no-pub --reporter expanded "--dart-define=QA_STUDENT_OUTPUT=$qaOutput"; Pop-Location
```

Kết quả đã chạy trên Windows: **44 passed, 0 failed, 0 skipped**, analyzer sạch. Mỗi mode có **52 classified + 6 rejected** từ fixture Phúc và **3 classified + 3 rejected** bổ sung: tổng **55 classified + 9 rejected**. Kiểm canonical text, TF-IDF indices/values, 20 E2, combined offset 8192, score/class/label/version/threshold/rule. Có Unicode code points ngoài BMP, IDNA, khoảng trắng Unicode, NUL và khoảng trắng hai đầu. Model loader kiểm thiếu file, kích thước/hash, JSON/schema, mode/threshold/feature order/IDF và cây lỗi. Test biên synthetic xác minh `score == threshold` thuộc phishing; fixture KD gần threshold nhất vẫn cách khoảng 0,0188042, không nhận là đã có URL sát ngưỡng trong sai số `1e-6`.

Sinh app QA Android riêng, chưa build/cài APK:

```powershell
& ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe tests\week7\prepare_student_runtime.py
```

Nếu `flutter` chưa có trong PATH, thêm `--flutter` với đường dẫn `flutter.bat` thực tế. App sinh tại `tests/week7/student_android/.android_harness` (ignored). Nó có application ID QA riêng, nạp KD để kiểm thử và ghi rõ Student thử nghiệm/score chưa calibrated. Hai test sau kiểm packaging/UI trên laptop, **không phải Android runtime**:

```powershell
Push-Location tests\week7\student_android\.android_harness; flutter pub get --enforce-lockfile; flutter analyze --no-pub; flutter test --no-pub --reporter expanded test/bootstrap_test.dart; Pop-Location
```

Đã chạy: analyzer sạch, **2 passed**, không fail/skip. Source test Android runtime và driver cũng được analyzer kiểm, nhưng chưa thực thi trên Android.

### Sau khi cài Android SDK và emulator

Platform Tools chứa `adb` chưa đủ build APK. Cài Android Studio, chọn SDK Platform **API 36**, Build-Tools, Command-line Tools, Emulator và **NDK (Side by side) 28.2.13676358**, cùng system image trong SDK Manager/Device Manager theo [hướng dẫn Flutter](https://docs.flutter.dev/platform-integration/android/setup). Bật Show Package Details để chọn NDK đúng phiên bản. Đây là `compileSdk`/NDK của Flutter 3.47.9; emulator có thể chạy API cao hơn, ví dụ API 37. Không đưa SDK vào repo. Tự đọc/chấp nhận licenses bằng `flutter doctor --android-licenses`, sau đó `flutter doctor -v` và `flutter devices`; doctor xanh không thay thế việc kiểm NDK/API riêng của project. Android CLI mới có thể báo `--licenses` không còn cần thiết; kiểm trạng thái licenses trong doctor thay vì xem cảnh báo deprecation là lỗi. Giữ Flutter phiên bản đã khóa cho lượt QA này.

Helper sinh app QA đặt `android.builtInKotlin=true` để khớp DSL Kotlin mà template Flutter 3.47.9/AGP 9 tạo ra, giữ nguyên compatibility flag `android.newDsl=false`. Nếu giữ built-in Kotlin tắt trong template này, Gradle không resolve được `kotlin.compilerOptions/jvmTarget`. Thay đổi chỉ áp dụng app QA generated, không sửa Gradle project của Hy; xem [hướng dẫn built-in Kotlin](https://docs.flutter.dev/release/breaking-changes/migrate-to-built-in-kotlin/for-app-developers).

Từ root QA, xác định đúng một Android target; nếu có nhiều máy, chọn ID mong muốn từ danh sách rồi gán `$qaAndroidId`:

```powershell
$qaDevices=flutter devices --machine | ConvertFrom-Json; $qaTargets=@($qaDevices | Where-Object { $_.targetPlatform -like 'android*' }); if ($qaTargets.Count -ne 1) { throw 'Cần chọn đúng một Android target từ flutter devices trước khi chạy.' }; $qaAndroidId=$qaTargets[0].id
```

Chạy app để smoke UI/offline hoặc chạy test parity thật (hai lệnh là hai lượt riêng; dừng `flutter run` trước lượt test):

```powershell
Push-Location tests\week7\student_android\.android_harness; flutter run -d $qaAndroidId; Pop-Location
```

```powershell
$env:QA_STUDENT_ANDROID_OUTPUT=Join-Path (Get-Location).Path 'reports/tables/week7/student_android_runtime.json'; Push-Location tests\week7\student_android\.android_harness; flutter drive --profile -d $qaAndroidId --driver=test_driver/integration_driver.dart --target=integration_test/student_runtime_test.dart; Pop-Location
```

Runtime test từ chối chạy trên desktop/web; so hai mode với cùng reference rồi mới đo inference KD (5 warm-up, 10 vòng × 55 URL). Report chứa build mode, OS/Dart, score deltas, p50/p95/mean và loader time. Đã thực thi trên **Android 17/API 37, x86_64 emulator**: 3 test ứng dụng passed (parity/performance, loader errors, UI), thêm 1 teardown framework; không gọi đó là 4 test nghiệp vụ. Mỗi mode 55 classified + 9 rejected, max score delta KD `1.1102230246251565e-16`, hard-only `5.551115123125783e-17`. UI test kiểm soát kênh bàn phím bằng Flutter TestTextInput để tránh native IME trả lại giá trị cũ khi inject text; model/assets/UI là thật, không nhận là kiểm bàn phím vật lý/native IME. Các lỗi thiếu model, hash sai và threshold sai đã chạy trong Android runtime.

Lượt offline profile đạt với airplane mode bật, Wi-Fi/data tắt, không có route; force-stop trước khi mở lại app test. Bằng chứng [`student_android_offline_runtime.json`](../reports/tables/week7/student_android_offline_runtime.json) được ghép với proof ADB trong [`student_android_verification.json`](../reports/tables/week7/student_android_verification.json). Raw Dart report không tự đọc trạng thái mạng OS. Có thể tái lập bằng cách bật airplane mode/tắt Wi-Fi và data trong emulator, xác nhận bằng `adb shell settings get global airplane_mode_on`, `adb shell settings get global wifi_on`, `adb shell settings get global mobile_data`, `adb shell ip route`, rồi chạy lệnh drive ở trên. Khôi phục mạng sau lượt kiểm.

Để ghi offline smoke: tắt Wi-Fi/mobile data hoặc bật airplane mode trên emulator, force-stop rồi mở app từ launcher; thử URL hợp lệ, URL lỗi port và nút parity; giữ USB/ADB để lấy log. Ghi trạng thái mạng, thiết bị/ABI/API, model/hash, từng expected/actual và ảnh/log. Không xem chặn `HttpClient` trong test host là Android OS đã tắt mạng.

Đo bổ sung sau parity, từ root QA (lệnh release x86_64 dành cho emulator đang dùng):

```powershell
Push-Location tests\week7\student_android\.android_harness; flutter build apk --release --target-platform android-x64 --target=lib/main.dart; Pop-Location
```

Helper dưới đây chỉ chấp nhận emulator và APK đúng application ID QA, cài APK, tắt mạng, thực hiện 3 lượt force-stop → launch → marker model ready, chạm Predict bằng accessibility/native ADB, lấy PSS/ảnh, rồi khôi phục mạng trong `finally`. `$qaSdk` là Android SDK Location thực tế; dòng dưới dùng vị trí mặc định Windows:

```powershell
$qaSdk=Join-Path $env:LOCALAPPDATA 'Android/sdk'; & ..\PhishGuardVN-w7-student-review\.venv\Scripts\python.exe tests\week7\measure_student_android.py "--adb=$qaSdk/platform-tools/adb.exe" --device=$qaAndroidId --apk=tests/week7/student_android/.android_harness/build/app/outputs/flutter-apk/app-release.apk --output=reports/tables/week7/student_android_release.json --screenshot=reports/figures/week7/student_android_release_offline.png
```

Đã chạy release offline từ launcher: model sẵn sàng cả 3 lượt, `example.com` trả benign bằng native touch không dùng keyboard stub, APK **18.498.267 bytes**, PSS sau prediction **87.208 KB**. Launch-to-ready đo tại host khoảng **1.800–2.174 ms**, có overhead ADB/polling; activity launch **1.559–1.680 ms** và loader **822–1.065 ms** được lưu riêng. Đây là process cold start với filesystem/shader cache giữ lại, không phải timing Android thuần hoặc khởi động máy mới. Profile inference offline (550 samples) có p50 **1,018 ms**, p95 **1,761 ms**, mean **1,101 ms**; không ghép với release loader thành một pipeline benchmark duy nhất. Assets/APK QA có thêm hard-only và fixtures, không dùng để tuyên bố kích thước production KD tối thiểu. Xem [`student_android_release.json`](../reports/tables/week7/student_android_release.json).

Chi tiết hiện hành: [`student_android_verification.json`](../reports/tables/week7/student_android_verification.json), [`student_dart_parity.json`](../reports/tables/week7/student_dart_parity.json). Student QA emulator đạt trong phạm vi trên; chưa kiểm thiết bị vật lý hoặc tích hợp Student vào app sản phẩm của Hy. Manifest/model Phúc giữ nguyên `android_verified=false` và `student_default=false`; kết quả QA được ghi riêng, không sửa artifact để đổi trạng thái. Teacher vẫn là engine mặc định. K7.3 Teacher Android và nghiệm thu cuối K7.5 không tự hoàn thành từ kết quả Student này.

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
