# Backend local — Issue #15

API v1: [contract](api_contract.md), Swagger `/docs`, schema `/openapi.json`. URL input chỉ phân tích offline, không mở website/DNS hoặc log raw URL. Teacher gọi loader/inference chính thức; E1/E2 numeric vẫn dùng `prediction.predict_url()` khi cấu hình tường minh.

## Cài từ checkout sạch — Teacher chính thức

Dùng **CPython 3.11** (runtime khác bị loader từ chối vì entropy có thể đổi nhánh cây). Code/lock/artifact chính thức có trong Git sau upstream `398ee2c`, đã vào main qua `7d2d600`; không cần cache riêng của Hưng. File bundle còn chữ candidate là tên lịch sử, không được đổi tên/sửa metadata để promotion.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-teacher.txt -e '.[api,test]'
python -m pip check
python scripts/predict_teacher.py --examples
export PHISHGUARD_BUNDLE_FORMAT=teacher
export PHISHGUARD_TEACHER_ROOT="$PWD"
export PHISHGUARD_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
unset PHISHGUARD_MODEL_BUNDLE PHISHGUARD_MODEL_NAME PHISHGUARD_MODEL_SHA256
python -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

PowerShell: `py -3.11 -m venv .venv`, `.venv\Scripts\Activate.ps1`; đặt `$env:PHISHGUARD_BUNDLE_FORMAT='teacher'`, `$env:PHISHGUARD_TEACHER_ROOT=(Get-Location).Path`, CORS tương tự; bỏ các override cũ bằng `Remove-Item Env:PHISHGUARD_MODEL_BUNDLE,Env:PHISHGUARD_MODEL_NAME,Env:PHISHGUARD_MODEL_SHA256 -ErrorAction SilentlyContinue`. Các command `python -m ...` không đổi.

Thứ tự pip ở trên giữ đúng versions Teacher; không nâng hàng loạt core libraries. Để chạy cả test suite upstream, thêm extras `teacher`/`research` và vẫn dùng `-r requirements-teacher.txt`. LightGBM test trên macOS cần `brew install libomp`; inference stacking thật chỉ cần các runtime libs trong requirements, không LightGBM/Torch. CI Linux đã có các job upstream tương ứng; API extras được thêm vào job hiện có để không skip API tests.

## Lock, health và lỗi cấu hình

`configs/teacher_lock.json` là release pointer, chỉ đọc. Loader `load_teacher(repo_root)` xác minh candidate lock hash, bundle SHA, Python/library versions, source/preprocessing/E2/reference và release status. Không deserialize file do caller chọn. API warm-up thật một lần/startup; sau đó tái sử dụng object, không train/tune, upload hoặc hot-reload. Đổi config cần restart.

- `/health` luôn 200 khi process sống; phải kiểm `model_ready` cho readiness.
- Ready: model là released `model_version`, feature_set là preprocessing version, protocol là lock operating_point_scope, artifact_sha256 là bundle trong lock.
- Thiếu release lock/bundle: degraded / artifact_missing. Hash/runtime/metadata/reference/warm-up sai: degraded / artifact_incompatible; POST URL hợp lệ trả 503. Không trả path/traceback/exception hoặc fallback E1/v1.
- `MODEL_BUNDLE`/`MODEL_NAME` không được dùng chung mode teacher. Optional `MODEL_SHA256` là pin bổ sung của đúng release lock; không hardcode candidate cũ.
- Mặc định format vẫn `v2` để giữ tương thích cũ; không cấu hình artifact thì not_configured/503. Không nhận Teacher thành công chỉ vì `/health` HTTP 200.

Xem [release guide của Phúc](teacher_v2_release.md) cho runtime, bundle và nguồn lock. Không đổi tên `teacher_v2_candidate.joblib`; release status thuộc lock/loader chính thức. API giữ nhãn, score và threshold do adapter trả, dùng `score >= threshold`; không gọi default classifier.predict ở ngưỡng .5.

## E1/E2 cũ — cấu hình tường minh, không fallback

Numeric E2 v1: `PHISHGUARD_BUNDLE_FORMAT=v2`, `PHISHGUARD_MODEL_BUNDLE=/path/to/trusted-bundle.joblib`, optional `PHISHGUARD_MODEL_NAME`, `PHISHGUARD_MODEL_SHA256`. Giữ guards feature/class/order/version/reference/source hashes và warm-up. Không giả định chỉ đổi đường dẫn numeric là load được stacking.

Cache H5.1 thật: `PHISHGUARD_BUNDLE_FORMAT=week5_e1_audit`, đặt MODEL_BUNDLE tới file cache thực và SHA từ handoff của file đó. Adapter chỉ đổi container trong bộ nhớ, không fit/clone/đổi weights/threshold .5. Đây là E1 lexical_12 lịch sử, **không phải Teacher stacking**; bằng chứng 09/11 được giữ riêng trong smoke records. Người clone không cần cache này để chạy Teacher chính thức. Không lấy digest E1 áp vào artifact Teacher.

## Smoke / bàn giao Khiêm #17

```sh
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{"url":"example.com"}'
curl -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{"url":"https://example.com:99999"}'
python -m pytest tests/test_api.py tests/test_api_teacher.py -q -rs
```

Windows dùng `curl.exe` hoặc JSON UTF-8 file với `--data-binary @request.json`. URL sai port luôn 422 trước readiness. Client TestClient phải dùng context manager cho lifespan: `with TestClient(create_app(bundle_format="teacher", teacher_root=repo_root)) as client:`. Factory đọc tham số tường minh; `api.app` đọc env lúc import.

Web port 3000/API 8000, CORS allowlist đúng origin, không wildcard/credentials. Không mở URL đích, không raw URL/body log hoặc lộ secrets. [Báo cáo API](../reports/week6_api_verification.md) và [Web](../reports/week6_web_verification.md) có kết quả/revision/hash thật. Fixtures unit chỉ kiểm logic, không tính là demo Teacher. QA/security/latency/clean-clone và final smoke chung vẫn phối hợp Khiêm #17; không nhắn riêng hoặc đánh dấu thay Khiêm.
