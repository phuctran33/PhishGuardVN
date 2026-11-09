# Week 6 — backend #15 và bàn giao contract

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
