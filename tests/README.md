# Chạy QA — Issue #17

## Runtime và source được kiểm

Teacher phát hành cần **CPython 3.11**, toàn bộ versions trong `requirements-teacher.txt`, cùng release lock/bundle chính thức. Môi trường Python 3.13 cũ không dùng cho nghiệm thu Teacher stacking.

Lần kiểm hiện tại dùng source backend PR #22 tại `7dfeec5f96f106f3544163466e2cf312494eb41f`, Web PR #23 tại `a2bb0dcedb7d12777774462a5fdea680aca2ff7e`. Teacher đã phát hành là `teacher-stacking-v2`, không còn là candidate mặc định. Đọc `docs/backend.md` và `docs/api_contract.md` của backend revision này.

Ví dụ dưới đây chạy từ gốc checkout QA, với checkout backend nằm cạnh nó. Điều chỉnh hai đường dẫn tương đối nếu bố trí thư mục khác:

```powershell
$backendRoot = (Resolve-Path ..\PhishGuardVN-pr22).Path;
$qaPython = (Resolve-Path ..\.qa-envs\release-311\Scripts\python.exe).Path;
& $qaPython -c "import sys, phishguard_vn.api as api; print(sys.version); print(api.__file__)";
& $qaPython -m pip check;
```

Trên máy khác, tạo venv CPython 3.11 tại đường dẫn tự chọn, rồi đặt `$qaPython` tới executable đó. Cài source backend được kiểm và runtime khóa phiên bản:

```powershell
& $qaPython -m pip install -r "$backendRoot\requirements-teacher.txt" -e "${backendRoot}[api,test]"
```

`api.__file__` phải trỏ tới backend được chọn. Bộ test sẽ báo lỗi nếu API và release root thuộc hai checkout khác nhau. Sau khi nhánh QA đã merge backend mới, có thể cài chính checkout QA và dùng nó làm `$backendRoot`.

## Full suite QA và Teacher thật

Dùng temp có GUID mới để tránh quyền thư mục pytest bị dùng chung giữa terminal người dùng và sandbox. Mỗi lệnh dưới đây đã có dấu chấm phẩy nên có thể paste thành một dòng:

```powershell
$qaTemp = Join-Path $env:TEMP ('phishguard-qa-' + [guid]::NewGuid().ToString('N')); $env:OMP_NUM_THREADS='1'; & $qaPython -m pytest -p no:cacheprovider -q -rs "--basetemp=$qaTemp" "--teacher-root=$backendRoot" --teacher-api
```

Kết quả đã kiểm trên working tree hiện tại: **490 passed, 2 skipped**. Hai skip là bộ tham số brand rỗng và handoff notebook 02/03 chưa có. Lệnh có `--teacher-api`, nên các ca API Teacher đã thực thi; không tính skip gate là pass. Số đếm thay đổi khi thêm test hoặc merge upstream; ghi SHA/source/môi trường thay vì sửa test cho khớp số cũ.

Chạy riêng phần Teacher/parity/security và benchmark:

```powershell
$qaTemp = Join-Path $env:TEMP ('phishguard-teacher-' + [guid]::NewGuid().ToString('N')); & $qaPython -m pytest -p no:cacheprovider -q -rs "--basetemp=$qaTemp" "--teacher-root=$backendRoot" --teacher-api tests\test_teacher_integration.py tests\test_api_benchmark.py
```

Kết quả đã kiểm: **53 passed**. Parity dùng 13 input và cùng artifact; tolerance score tuyệt đối `1e-12`. Nhãn Teacher theo `score >= threshold`; ngưỡng đọc từ lock, không mặc định .5.

## Kiểm lại test nguyên bản PR #22

Chạy từ gốc checkout backend, dùng `$qaPython` đã đặt là đường dẫn tuyệt đối:

```powershell
Set-Location $backendRoot; $apiTemp=Join-Path $env:TEMP ('phishguard-pr22-'+[guid]::NewGuid().ToString('N')); & $qaPython -m pytest -p no:cacheprovider -q -rs --tb=short "--basetemp=$apiTemp" tests\test_api.py tests\test_api_teacher.py
```

Bản `7dfeec5` trên Windows hiện **47 passed, 1 failed** tại test offline do chặn socketpair khi TestClient khởi tạo event loop. Chi tiết QA-WIN-01 được ghi trong `reports/week6_api_qa.md` để phản hồi trực tiếp trên PR #22. Source test nguyên bản chưa được sửa trong lần QA này; bản sao thử đề xuất đạt 48/48.

Full upstream suite cần thêm extras `teacher,research` theo hướng dẫn backend, vẫn giữ `-r requirements-teacher.txt`. Khi đối chiếu tác vụ này, loại đúng bài `test_real_external_bundle_matches_saved_scores` bằng `-k`; không huấn luyện project data, chấm Official Test hoặc chạy benchmark external mới. Kết quả đã ghi: **552 passed, 2 skipped, 1 failed, 1 deselected**.

## Chạy backend thật và đo latency

Trong terminal backend, đặt cấu hình Teacher và xóa các override numeric cũ:

```powershell
$env:PHISHGUARD_BUNDLE_FORMAT='teacher'; $env:PHISHGUARD_TEACHER_ROOT=$backendRoot; $env:PHISHGUARD_CORS_ORIGINS='http://127.0.0.1:3000,http://localhost:3000'; $env:OMP_NUM_THREADS='1'; Remove-Item Env:PHISHGUARD_MODEL_BUNDLE,Env:PHISHGUARD_MODEL_NAME,Env:PHISHGUARD_MODEL_SHA256 -ErrorAction SilentlyContinue;
& $qaPython -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Giữ terminal đó chạy. Trong terminal QA khác, kiểm health và đo; đặt lại `$qaPython` nếu chưa khai báo trong terminal mới:

```powershell
curl.exe -i http://127.0.0.1:8000/health;
& $qaPython scripts\benchmark_api_latency.py --base-url http://127.0.0.1:8000 --url https://example.com/login --warmup 10 --requests 100 --output reports\tables\week6\api_latency_teacher_local.json
```

Health phải `model_ready=true`, model/hash đúng release lock. Kết quả đã lưu ở `api_latency_teacher.json`: mean **16.0741 ms**, p95 **19.8404 ms**, 100 requests sau 10 warm-up, HTTP keep-alive/concurrency 1 trên Windows CPython 3.11.14. Kết quả máy khác có thể khác. Công cụ từ chối health degraded, response sai contract hoặc mất kết nối; không tạo số đo thành công giả và không ghi raw URL.

PowerShell smoke POST ổn định qua JSON UTF-8 file:

```powershell
$bodyPath=Join-Path $env:TEMP ('pgvn-request-'+[guid]::NewGuid().ToString('N')+'.json'); [IO.File]::WriteAllText($bodyPath,'{"url":"example.com"}',[Text.UTF8Encoding]::new($false)); curl.exe -i -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' --data-binary "@$bodyPath"
```

## Web và final E2E

Từ `apps/web` của checkout PR #23:

```powershell
flutter pub get;
flutter analyze;
flutter test;
flutter build web --release --no-web-resources-cdn --dart-define=API_BASE_URL=http://127.0.0.1:8000;
& $qaPython -m http.server 3000 --bind 127.0.0.1 --directory build/web
```

Mở `http://127.0.0.1:3000`. Ghi SHA backend/Web/QA, hash artifact, runtime, từng bước và kết quả:

| Tình huống | Kiểm tra |
| --- | --- |
| URL hợp lệ | POST 200; nhãn/model/score/rule hiển thị đúng response. Thử `https://example.com/Login?Q=A`: score khoảng .576056 nhưng vẫn benign theo ngưỡng lock. |
| URL sai | `https://example.com:99999` trả 422 `invalid_port`; UI báo lỗi và sửa input được. |
| Backend mất kết nối | Dừng process backend thật, gửi lại từ Web; loading kết thúc, có lỗi/retry. Bật lại cùng artifact/port; retry thành công trên cùng trang. |

Đã kiểm đủ ba tình huống với Teacher thật, thêm empty/no POST, phishing từ ví dụ bàn giao, thiếu model/503 và năm viewport. Bằng chứng tại `reports/tables/week6/release_e2e.json`, ảnh `reports/figures/week6/khiem_teacher_*.png`. Widget tests dùng HTTP mock; kết quả browser nêu trên gọi API/model thật. Test viewport không phải test Android vật lý.

## CI, merge và clean clone cuối

`.github/workflows/tests.yml` checkout backend/Teacher đúng SHA được review, cài runtime khóa phiên bản, chạy full QA với `--teacher-api` và gate Teacher riêng. Diff này chưa được push/chạy trên Actions; trạng thái xanh của commit cũ không chứng minh diff mới.

Nhánh QA hiện có thay đổi chưa commit, nên không tự merge hoặc tạo merge commit. Sau khi tự kiểm và commit phần QA, người phụ trách cập nhật backend vào cùng nhánh, xử lý conflict cấu hình nếu có, rồi cài lại source của nhánh vừa hợp nhất và chạy tests. Cuối cùng push, kiểm Actions và clean clone **đúng revision đó**.

Sau commit QA do người phụ trách thực hiện, có thể chuẩn bị merge để xem trước mà chưa tạo merge commit:

```powershell
git fetch origin feat/w6-fastapi-backend;
git merge --no-commit --no-ff origin/feat/w6-fastapi-backend
```

Kiểm tra diff/conflicts, giữ đầy đủ các extras upstream và cấu hình pytest của QA, chạy lại tests rồi người phụ trách mới tự commit merge. Nếu backend đã có commit sửa QA-WIN-01, cập nhật SHA pin trong workflow theo revision vừa kiểm.

Clean clone phải có đủ bằng chứng: `git rev-parse HEAD`, tạo venv CPython 3.11 mới, cài theo README và requirements lock, `pip check`, pytest, startup backend và GET `/health`. Ghi pass/fail/skip/blocker riêng; health 200 nhưng degraded không phải inference thành công. Baseline clean clone `cef4aea` đã có 439 passed/2 skipped và smoke không model; revision QA mới chưa được xác nhận clean clone.

Tests/security/CI/clean clone giữ hạn 14/11/2026; final E2E trước nghiệm thu 15/11. Khi báo lỗi, ghi revision/môi trường/lệnh/expected/actual; ẩn URL riêng tư, token và đường dẫn cá nhân. Lịch sử Teacher v1/candidate trong `reports/history/week6_api_qa_pre_release.md`; runtime và kết quả hiện tại lấy từ báo cáo release mới.
