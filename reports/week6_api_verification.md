# Week 6 — API #15: released stacking integration, 13/11/2026

Upstream chính thức `398ee2ce9e587644ebe21b529fba485536a9aac1`, PR #26 đã vào main qua PR #27, main base `7d2d60091c971dd3081b0b71fbf35b4cdd80c165`. PR #22 giữ base main; không đưa benchmark của Phúc vào diff API. Contract v1 đã bàn giao trước implementation từ `b610bab`; thay đổi bổ sung hiện tại là threshold-rule và optional threshold, đồng bộ PR #23.

## Teacher và contract hiện tại

- `load_teacher(repo_root)` chính thức, không load candidate trực tiếp; `configs/teacher_lock.json` là release pointer. Giữ tên file lịch sử `teacher_v2_candidate.joblib` và bytes gốc.
- Model **teacher-stacking-v2**, preprocessing **canonical-reference-v1**, protocol **full_train_group_oof_fpr_target_0.01**. Artifact SHA256 **63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1**.
- Runtime thực **CPython 3.11.17**, đúng bảy package versions trong `requirements-teacher.txt`. Không dùng 3.12/3.14 để ép load, không sửa entropy/E2/reference/threshold.
- Threshold đọc từ lock/adapter: **0.6945740700635259**; decision rule **score >= threshold**, score meta-LR chưa hiệu chuẩn. Các số ở đây là kết quả đọc lock của lượt chạy, không phải constants trong code.
- API giữ validation/trim v1, truyền chuỗi đã trim nguyên cho adapter. Canonical text và raw E2 do pipeline Phúc xử lý. Nhãn lấy nguyên từ adapter, không gọi estimator.predict ở .5. Numeric E1/E2 vẫn có cấu hình tường minh và response 7 trường cũ; stacking thêm threshold.
- Load một lần/startup, warm-up thật trước ready; hash/runtime/library/metadata/source/reference guards do loader chính thức kiểm. Sai lock/artifact/runtime/warm-up: health degraded, predict 503, không fallback E1/v1. CORS/error/privacy giữ nguyên.

## Kiểm chứng thực tế

| Kiểm tra | Kết quả |
|---|---|
| Focused `tests/test_api.py tests/test_api_teacher.py` | **48 passed**, 0 failed |
| Full available pytest, kèm teacher/research extras | **554 passed, 1 skipped, 1 deselected, 3 warnings** |
| Python CLI chính thức ↔ HTTP API, cùng bundle/input | **13/13 khớp**, max absolute score delta **0.0**, atol **1e-12**; label, threshold và rule trùng tuyệt đối |
| Input sai (rỗng/port/scheme/whitespace bên trong) | **4/4 trả 422**, không echo raw input |
| API no-network test với bundle thật | Chặn getaddrinfo/create_connection/socket.connect; startup warm-up và predict vẫn pass |
| Interpreter 3.14 thật | Health degraded / predict 503, không ép load Teacher; unit guards upstream cũng chặn 3.10/3.12/3.13 |
| HTTP readiness / Swagger / OpenAPI | Health ready với đúng version/protocol/hash; Swagger/schema giữ v1 và thêm threshold-rule |
| Frozen nghiên cứu upstream | Source/lock/model/data/reference/notebook/experiment checkout bytes không sửa so với main base; so theo .gitattributes, giữ CRLF bắt buộc của research plan |

13 URL gồm thiếu scheme, HTTPS, hostname hoa/thường, path/query/escaping, scheme-relative, port hợp lệ, Unicode/punycode, IPv4/IPv6 và 1 URL thuộc **Validation** (ID `024efd11-58b4-57c4-8d40-383a1034b19f`, split đã kiểm là val) để phủ nhánh phishing. Không mở website. `https://example.com/Login?Q=A` có score **0.5760558654872865**, adapter trả **benign**, chứng minh không suy nhãn ở .5. Đây là kiểm tra protocol/integration, không benchmark hoặc ước lượng chất lượng.

Skip duy nhất là empty parameter set cũ ở `test_brand_regressions.py:58`. Deselect đúng test `test_real_external_bundle_matches_saved_scores` vì tác vụ không chạy external; không sửa/xóa test hoặc assertion. Regression 1.585 Validation có sẵn của upstream vẫn pass; không score Official Test. Research tests chỉ fit fixtures toy, không train/retrain Teacher/project data. Ba warnings thuộc upstream pandas/sklearn API deprecations.

Lượt full đầu có lỗi LightGBM thiếu libomp trên macOS. Đã cài đủ research extras và Homebrew libomp 23.1.4; lượt full cuối chạy môi trường bình thường, không DYLD override: **554 passed, 1 skipped, 1 deselected, 3 warnings in 31.44s**. Không sửa code upstream/guards để pass. `uv pip check` báo tất cả packages tương thích. CI Linux giữ jobs upstream, chỉ bổ sung api extra để chạy API tests thay vì skip; CI fixtures không thay thế bằng chứng bundle thật.

JSON từng URL, response, runtime versions và hashes source được kiểm tra: [api_smoke.json](tables/week6/api_smoke.json), mục **current_teacher**. Mục **legacy_e1_2026_11_09** giữ nguyên record E1 cũ; không gọi kết quả E1 là Teacher.

## Bàn giao và giới hạn

[API contract](../docs/api_contract.md), [cài/chạy Teacher](../docs/backend.md), Base URL `http://127.0.0.1:8000`, Swagger `/docs`, Web/CORS port 3000. Không cần cache riêng của Hưng; bundle/locks đã có trong checkout Git chính thức. Không sửa `candidate_only/promoted/finalized` của artifact, không train/tune/benchmark/external/Official Test, KD hoặc Android.

#15 đáp ứng DoD backend; không phụ thuộc KD/Android để review. #19 có bằng chứng Web → API → Teacher riêng. Khiêm #17 tiếp tục QA/security/latency/clean-clone và final smoke nghiệm thu; không đánh dấu thay Khiêm và không nhắn riêng.

---

Các đoạn dưới đây là lịch sử E1 ngày 09/11, giữ để phân biệt nguồn bằng chứng. Nhận xét “chưa có Teacher” chỉ áp dụng tại thời điểm cũ; Teacher hiện tại đã được tích hợp ở phần trên.

# Lịch sử E1 — 09/11/2026 (không phải bằng chứng stacking)

Base kiểm tra: main `5509ed1`. Contract commit trước implementation: `b610bab`, [API v1](../docs/api_contract.md). Không tự merge, không train/tune model hoặc chạy external để lựa chọn.

## Kết quả thực tế

- `python -m pytest tests/test_api.py -q -rs`: **33 passed**. Fixtures estimator trong unit tests là synthetic, không dùng cho demo.
- Full suite với handoff local có sẵn được sao chép nguyên bytes: **420 passed, 1 skipped, 1 warning in 18.31s**. Skip cũ: empty parameter set ở `tests/test_brand_regressions.py:58`. Warning cũ: invalid escape trong `week5_reporting.py:148`; không sửa code đã hoàn thành ngoài scope.
- Venv mới cài bằng `pip install -e '.[api,test]' tldextract==5.4.0 idna==3.20`: **33 backend tests passed in 13.36s**. Không nhầm bước này với toàn bộ clean-clone/security/CI QA thuộc #17.
- Uvicorn thật `127.0.0.1:8000`: GET health/docs/openapi đều 200; health ready; POST /predict dùng pipeline E1 thật. Bảy HTTP checks đều đạt: URL hợp lệ, rỗng, thiếu scheme, port sai, Unicode hostname, IPv4, IPv6. Kết quả JSON tại [api_smoke.json](tables/week6/api_smoke.json).
- API trong venv mới, không cấu hình model, `127.0.0.1:8001`: health 200/degraded/not_configured, docs 200, POST URL hợp lệ 503/MODEL_UNAVAILABLE. Không fake prediction khi clone không có artifact. Các lần gọi kiểm chứng thực hiện sau khi Uvicorn báo startup complete.
- Tests kiểm tra load một lần, probability/margin khác nhau, lỗi input trước readiness, không echo input/traceback, CORS allowlist, thiếu/hỏng artifact, hash/class/order/version sai và E2 source hash guard.

## Artifact demo thật và giới hạn

Pipeline cache H5.1: `data/interim/week5/e1_result.joblib`, SHA256 `6bd8324a56bba9f98615599419349947f461f77d6a9e11f578db22836dd6014c`, selected_model **logistic_regression_balanced**, lexical_12, threshold .5. Cache không bị ghi lại hoặc đưa lên Git. Adapter chỉ đổi container trong bộ nhớ để gọi predict_url; protocol công bố `week5_e1_audit`, không nhận là bundle ablation hoặc Teacher v1 của Phúc.

13,078 Core Train IDs × 12 features của cache và representation hiện tại khớp **max abs delta = 0.0**. Đây là so representation đã có, không tái chạy thí nghiệm, không dùng Official Test để chọn model/threshold. Runtime Python 3.14.0, numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1, joblib 1.6.0, tldextract 5.4.0, idna 3.20. API: FastAPI 0.162.2, Starlette 1.10.0, Pydantic 2.14.3, Uvicorn 0.54.0; TestClient dùng httpx2 2.16.0.

Input example.com trả benign, score `0.4949721386878221` (predict_proba chưa hiệu chuẩn); **không phải** metric/đảm bảo URL an toàn. Thiếu Teacher từ #16 vẫn là blocker tích hợp Teacher, không chặn backend/current-model demo. E2 v1 compatibility đã được kiểm tra bằng fixtures/metadata guards, chưa có inference bằng Teacher E2 thật. Không bỏ guard hoặc đổi schema v0 để làm pass.

## Bảo toàn / bàn giao

Ngoài README và pyproject (thêm optional API/test dependencies), mọi tracked file có sẵn trên base giữ nguyên bytes: raw data, labels, splits/folds, parser/features/prediction.py/reference, notebook outputs, frozen manifests, model metadata và experiment metrics. Model cache SHA256 cũng giữ nguyên. Code backend mới nằm trong `src/phishguard_vn/api.py`, smoke tests trong `tests/test_api.py`.

Hướng dẫn từ máy mới/cấu hình artifact/curl/TestClient: [backend.md](../docs/backend.md). Base URL cho Khiêm: `http://127.0.0.1:8000`; Swagger `/docs`; CORS cấu hình cho `http://localhost:3000,http://127.0.0.1:3000`. Không công khai URL nhạy cảm, không truy cập URL đích hoặc log raw URL. QA/security/CI/latency đầy đủ và clean-clone acceptance vẫn thuộc #17, không đánh dấu thay Khiêm.
