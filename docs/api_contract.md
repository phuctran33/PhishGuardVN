# PhishGuardVN API contract — v1

Contract bàn giao cho #17 và #19; chốt trước implementation trong #15. Base URL local: `http://127.0.0.1:8000`. Không authentication/database. API chỉ phân tích chuỗi offline bằng `prediction.predict_url()`, không mở URL, không DNS/HTTP tới website đích. Không gửi URL nhạy cảm vào demo công khai.

## GET /health

Luôn trả **200** khi tiến trình API hoạt động, kể cả chưa có model. Readiness nằm ở `model_ready`, không suy ra từ HTTP 200.

```json
{
  "status": "degraded",
  "model_ready": false,
  "model": null,
  "feature_set": null,
  "protocol": null,
  "artifact_sha256": null,
  "model_error": "not_configured"
}
```

| Trường | Kiểu / ý nghĩa |
|---|---|
| status | `ok` nếu model sẵn sàng, ngược lại `degraded` |
| model_ready | boolean; chỉ true sau khi load, kiểm tra metadata/schema và warm-up inference thật thành công |
| model | string hoặc null; model được chọn trong bundle |
| feature_set | `lexical_12`, `e2-brand-v1` hoặc null |
| protocol | string từ bundle, hoặc `week5_e1_audit` cho adapter cache E1, hoặc null |
| artifact_sha256 | SHA256 file artifact đã load, hoặc null |
| model_error | null hoặc một trong `not_configured`, `artifact_missing`, `artifact_load_failed`, `artifact_incompatible`; không chứa đường dẫn/exception |

Model được load **một lần trong lifespan startup**, không load theo từng request. `/docs` là Swagger, `/openapi.json` là schema máy đọc được. Đổi artifact/config cần restart API.

## POST /predict

Header `Content-Type: application/json`. Body bắt buộc là object gồm **duy nhất** trường `url`:

```json
{"url": "https://example.com"}
```

`url` bắt buộc là string, 1–4096 Unicode code points trước trim; không chấp nhận null/number/bool/list, trường khác hoặc chuỗi chỉ whitespace. Bỏ whitespace hai đầu; không chấp nhận whitespace/control character bên trong. Chỉ cho HTTP(S), URL thiếu scheme và scheme-relative theo parser hiện có. API không lower-case path/query, không tự sửa hostname hoặc port.

- `example.com/path` và `//example.com/path`: được parser thêm scheme để phân tích, không truy cập mạng.
- Unicode hostname, IPv4, IPv6 có ngoặc vuông: chấp nhận nếu parser trả is_valid.
- Port ngoài 0–65535/không phải số, hostname lỗi, suffix không resolve: 422.
- `ftp://example.com`: 422 `unsupported_scheme`; API chỉ phục vụ HTTP(S).
- `http://[2001:db8::1]/`: input kỹ thuật hợp lệ; model không bảo đảm chất lượng trên IP/out-of-distribution.

### 200 — inference thành công

Tất cả bảy trường dưới đây luôn có mặt:

| Trường | Kiểu / ý nghĩa |
|---|---|
| label | `phishing` hoặc `benign`, từ estimator.predict, không từ ngưỡng UI |
| model | string, tên model đã load |
| score | số hữu hạn; probability thuộc [0,1], decision_function không bị giới hạn khoảng |
| score_kind | `probability` hoặc `decision_function` |
| score_definition | string giải thích score từ predict_url |
| decision_rule | `estimator.predict` |
| protocol | string theo bundle; không suy ra Teacher v1 chỉ từ tên API |

Ví dụ **inference thật đã kiểm tra trên pipeline E1 local**, không phải kết quả Teacher/external: input `https://example.com`, cache `e1_result.joblib` SHA256 `6bd8324a56bba9f98615599419349947f461f77d6a9e11f578db22836dd6014c`. Adapter chỉ đổi container trong bộ nhớ, không fit/chỉnh weights hoặc thay threshold 0.5. Protocol adapter mô tả nguồn cache, không nhận là protocol ablation E2 của Phúc.

```json
{
  "model": "logistic_regression_balanced",
  "label": "benign",
  "score": 0.4949721386878221,
  "score_kind": "probability",
  "score_definition": "predict_proba cho phishing; chưa hiệu chuẩn nguy cơ thực tế",
  "decision_rule": "estimator.predict",
  "protocol": "week5_e1_audit"
}
```

SVM dùng decision margin: **không** thêm `%` hoặc gọi là xác suất. `probability` là predict_proba của lớp phishing, chưa hiệu chuẩn nguy cơ thực tế. Nhãn benign không đồng nghĩa URL chắc chắn an toàn. Không trả lại raw URL hoặc feature vector trong response.

### Error schema thống nhất

```json
{
  "error": {
    "code": "INVALID_URL",
    "message": "URL không hợp lệ hoặc tên miền không được parser hỗ trợ.",
    "reason": "invalid_port"
  }
}
```

`error.code`, `error.message`, `error.reason` luôn là string. Client nên xử lý theo code/reason; message tiếng Việt là nội dung hiển thị, không chứa raw input, file path, traceback hoặc exception detail.

| HTTP | code | reason / trigger |
|---|---|---|
| 422 | INVALID_REQUEST | `invalid_json`: JSON malformed; `schema_validation`: thiếu/sai kiểu/extra field/url rỗng/whitespace/URL dài quá 4096 |
| 422 | INVALID_URL | `unsupported_scheme`, `invalid_characters`, `invalid_port`, `invalid_hostname`, `unresolved_domain`, `parse_error` |
| 503 | MODEL_UNAVAILABLE | Một trong bốn model_error của /health; input hợp lệ nhưng model chưa sẵn sàng |
| 500 | INFERENCE_FAILED | `prediction_failed`: lỗi inference/response không hợp lệ; không fallback sang nhãn/score giả |
| 500 | INTERNAL_ERROR | `internal_error`: exception ngoài dự kiến, response được che chi tiết |
| 404 | NOT_FOUND | `not_found`: route không tồn tại |
| 405 | METHOD_NOT_ALLOWED | `method_not_allowed`: ví dụ GET /predict; giữ HTTP Allow header |

Thứ tự: validate body → validate URL → kiểm tra model → inference. Vì vậy URL sai vẫn trả 422 khi model chưa cấu hình. Preflight `OPTIONS` thuộc CORSMiddleware: origin không được phép có thể nhận 400 plain text của middleware, không thuộc schema lỗi route nêu trên. Browser không được nhận allow-origin cho origin ngoài allowlist.

Ví dụ không hợp lệ:

```json
{"url": ""}
```

422 INVALID_REQUEST / schema_validation. `{"url":"https://example.com:99999"}` trả 422 INVALID_URL / invalid_port. `{"url":"example.com","model":"x"}` trả 422 vì không cho client chọn artifact/model qua body.

## Cấu hình và chạy local

Python >=3.11, dùng virtual environment. Từ repository root sau khi backend trong #15 được thêm:

```sh
python -m pip install -r requirements.txt
python -m pip install -e '.[api,test]'
export PHISHGUARD_MODEL_BUNDLE=/absolute/path/week5_e2_ablation.joblib
export PHISHGUARD_BUNDLE_FORMAT=v2
export PHISHGUARD_MODEL_NAME=mlp
export PHISHGUARD_MODEL_SHA256=sha256_do_phuc_ban_giao
export PHISHGUARD_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
python -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Trên PowerShell dùng `$env:PHISHGUARD_MODEL_BUNDLE='C:\path\model.joblib'` tương tự cho biến khác; command pip/uvicorn không đổi. SHA là 64 ký tự hex thực của file; bỏ biến nếu chưa có digest để không dùng placeholder làm cấu hình chạy. Chỉ load joblib local từ người bàn giao tin cậy; request không nhận URL tải model hoặc path artifact.

| Biến | Mặc định / tác dụng |
|---|---|
| PHISHGUARD_MODEL_BUNDLE | Không cấu hình: startup vẫn chạy, health degraded, predict 503 |
| PHISHGUARD_BUNDLE_FORMAT | `v2`: bundle từ Phúc; `week5_e1_audit`: adapter cache E1 hiện có, không phải Teacher |
| PHISHGUARD_MODEL_NAME | model selected trong bundle nếu không đặt |
| PHISHGUARD_MODEL_SHA256 | tùy chọn; nếu đặt phải khớp trước deserialize |
| PHISHGUARD_CORS_ORIGINS | rỗng: không cho browser cross-origin; CSV các origin cụ thể, không dùng wildcard/credentials |

Bundle v2 phải khớp feature order, fitted model/classes 0/1, score kind và protocol. E2 phải là **e2-brand-v1**, reference snapshot khớp reference hiện tại (45 brands), source hashes extractor khớp LF-normalized; v0 không được đổi tên thành v1. Mỗi lần startup thử inference bằng example.com offline trước khi báo ready. Teacher mới thay qua config, không sửa frontend/backend.

Để demo bằng E1 cache có sẵn, đặt bundle path đến `data/interim/week5/e1_result.joblib`, format `week5_e1_audit`, bỏ model_name nếu không override. Adapter chỉ dùng pipeline đã fit/selected_model/feature_names trong cache, đòi threshold 0.5 và Test chưa đánh giá theo scope; không chạy train. Cache không nằm trong Git: clean clone thiếu artifact phải trả degraded/503, không được nhận là demo inference thật đã hoạt động.

```sh
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/predict -H 'Content-Type: application/json' -d '{"url":"example.com"}'
```

## Bàn giao cho Khiêm

Tests có thể dùng `from phishguard_vn.api import create_app`, rồi `with TestClient(create_app(...)) as client` để chạy lifespan thật. Factory nhận `bundle_path`, `bundle_format`, `model_name`, `expected_sha256`, `cors_origins`; cấu hình truyền trực tiếp ưu tiên hơn biến môi trường. Chi tiết tests hiện có và cách chạy nằm trong README backend. Fixtures giả chỉ dùng trong unit tests, không phải artifact/demo nghiệm thu.

Kiểm tra cả health degraded/503 và model ready; body-invalid phải 422 trước readiness; không echo URL lỗi; CORS đúng allowlist. #17 tiếp tục phụ trách QA/security/CI đầy đủ và clean clone; #15 chỉ bổ sung smoke tests implementation. Sau #19 có hướng dẫn môi trường Web → API → model thật để Khiêm hậu kiểm. Nếu đổi contract, phải cập nhật tài liệu/OpenAPI/tests và ghi rõ thay đổi khi bàn giao; không âm thầm đổi score semantics hoặc error schema.
