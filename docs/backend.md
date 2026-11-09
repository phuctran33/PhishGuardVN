# Backend local — Issue #15

API contract v1: [api_contract.md](api_contract.md). Base URL `http://127.0.0.1:8000`, Swagger `/docs`, schema `/openapi.json`. Backend gọi đúng `phishguard_vn.prediction.predict_url`; không train, không crawl/DNS URL người dùng hoặc lưu lịch sử.

## Cài từ checkout sạch

Từ root repository, Python >=3.11:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[api,test]' tldextract==5.4.0 idna==3.20
python -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

PowerShell: dùng `.venv\Scripts\Activate.ps1`; các command `python -m ...` không đổi. Không cần cài Jupyter chỉ để chạy API. Môi trường inference phải tương thích phiên bản scikit-learn/numpy/joblib của artifact; không ép load artifact khi sklearn báo khác version.

Checkout sạch **không có model binary**. API vẫn khởi động: `/health` trả 200 với `status=degraded`, `model_ready=false`, `model_error=not_configured`; POST URL hợp lệ trả **503**, không có prediction giả. `/health` là liveness; kiểm tra model_ready cho readiness. Không nhận demo model thành công chỉ vì health 200.

## Cấu hình artifact thật

Bundle chuẩn v2 từ Phúc, ví dụ E2 v1:

```sh
export PHISHGUARD_MODEL_BUNDLE=/absolute/path/week5_e2_ablation.joblib
export PHISHGUARD_BUNDLE_FORMAT=v2
export PHISHGUARD_MODEL_NAME=mlp
export PHISHGUARD_MODEL_SHA256=SHA256_DO_PHUC_BAN_GIAO
export PHISHGUARD_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
python -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Thay `SHA256_DO_PHUC_BAN_GIAO` bằng digest thực; có thể bỏ biến SHA khi chưa được bàn giao, nhưng nên pin digest cho demo tái lập. Trên PowerShell dùng `$env:PHISHGUARD_MODEL_BUNDLE='C:\path\model.joblib'` và tương tự cho các biến khác. Không đưa secrets hoặc model binary vào Git.

Chỉ load joblib local từ nguồn tin cậy: định dạng này có thể thực thi code lúc deserialize. API caller chỉ được gửi URL, không được chọn artifact, model hoặc path. SHA được đối chiếu trước deserialize khi có cấu hình. Sau load, kiểm tra feature order, class order 0/1, score method, protocol và warm-up inference thật; E2 cần đúng v1, snapshot reference hiện tại và hashes ba extractor LF-normalized. Model không phù hợp làm health degraded / predict 503; không tự đổi v0 thành v1.

Thay Teacher khi #16 bàn giao bằng đổi biến cấu hình và restart, không viết lại API/Web. Phiên bản/schema/reference phải đúng; không có endpoint upload hoặc hot-reload model.

### Dùng E1 hiện có khi chưa có Teacher

Nếu máy đã có **cache H5.1 thật** `data/interim/week5/e1_result.joblib`:

```sh
export PHISHGUARD_MODEL_BUNDLE="$PWD/data/interim/week5/e1_result.joblib"
export PHISHGUARD_BUNDLE_FORMAT=week5_e1_audit
unset PHISHGUARD_MODEL_NAME
export PHISHGUARD_MODEL_SHA256=6bd8324a56bba9f98615599419349947f461f77d6a9e11f578db22836dd6014c
export PHISHGUARD_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
python -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Digest trên chỉ áp dụng cache local đã dùng cho bằng chứng lần này; không áp cho artifact Phúc hoặc file khác. Trên PowerShell bỏ override model bằng `Remove-Item Env:PHISHGUARD_MODEL_NAME -ErrorAction SilentlyContinue` và thay `$PWD/...` bằng đường dẫn thực.

Adapter `week5_e1_audit` chỉ đặt pipeline đã fit vào container mà predict_url nhận; không clone/fit/tune/change weights, giữ threshold .5, đòi scope `test_evaluated=false`. Model là **logistic_regression_balanced / lexical_12**, protocol báo `week5_e1_audit`; **không phải Teacher E2 v1**. Cache này không phân phối trong Git; nếu không có file thì giữ degraded/503, nhận artifact thật từ người bàn giao, không train để làm demo.

Đã đối chiếu 13,078 Train IDs × 12 features của cache với representation hiện tại: max absolute difference = 0.0. Parser chỉ đổi accessor tldextract registered_domain → top_domain_under_public_suffix, cùng tldextract 5.4.0; không sửa source/provenance hoặc gọi weights này là E2. Đây là kiểm tra tương thích cache hiện có, không phải thí nghiệm/đánh giá model mới.

## Smoke bằng curl

```sh
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{"url":"example.com"}'
curl -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{"url":"https://example.com:99999"}'
```

Input cuối trả 422 INVALID_URL/invalid_port kể cả chưa có model. Dùng `curl.exe` trên Windows để tránh alias PowerShell cũ; JSON có thể đặt vào file UTF-8 và gửi bằng `--data-binary @request.json`.

## Handoff cho Khiêm (#17)

- Contract, schema lỗi và ví dụ: [api_contract.md](api_contract.md); Swagger và schema live ở các path trên.
- Start API + CORS như trên. Web dùng port 3000. Default origin allowlist rỗng; không dùng wildcard hoặc credentials.
- Tests: `python -m pytest tests/test_api.py -q`; toàn bộ suite: `python -m pytest -q -rs`.
- TestClient: `with TestClient(create_app(bundle_path=..., bundle_format=..., cors_origins=[...])) as client:`. Factory chỉ dùng tham số truyền trực tiếp; `api.app` đọc env khi import. Lifespan cần context manager. Fixtures synthetic trong unit tests không phải demo inference thật.
- Model load một lần/startup. App lỗi artifact vẫn phục vụ health/docs để clean-clone test thấy rõ file/config còn thiếu.
- Không bật debug, không log raw URL/body; command chạy tắt access log để không lưu URL query của request. Không trả traceback/path/exception detail.
- #15 cung cấp smoke/contract tests, không thay toàn bộ QA/security/latency/CI của #17. Xem báo cáo kiểm chứng thực tế đi kèm; Teacher #16 và smoke Web hậu kiểm #19 được phân biệt với kết quả E1 hiện tại.
