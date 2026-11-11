# Báo cáo QA API — Issue #17

## Phạm vi và môi trường

- Nhánh kiểm tra: `test/api-contract-qa`, dựa trên nhánh backend PR #22.
- Lần chạy ghi nhận: 10/11/2026.
- Hệ điều hành: Windows, chạy bằng PowerShell.
- Python: 3.13.7.
- Gói được cài từ `pyproject.toml` với extra `api,test`; `tldextract` 5.4.0 và `idna` 3.20.
- Test API dùng estimator và artifact tổng hợp trong thư mục tạm; không dùng model thật.
- Artifact `week5_e2_ablation.joblib` không có trong checkout này. Không đặt biến môi trường model theo đường dẫn ví dụ.

## Kết quả

- `tests/test_api.py`: **41 passed**.
- Toàn bộ pytest suite: **435 passed, 2 skipped**.
- `pip check`: không có dependency lỗi.
- `git diff --check`: không có lỗi whitespace.

Hai test bị skip:

- `tests/test_brand_regressions.py:58`: fixture không sinh ra bộ tham số brand regression.
- `tests/test_splits.py:210`: chưa có handoff dữ liệu local từ notebook 02 và 03.

Lúc chuẩn bị môi trường QA, full suite ban đầu báo thiếu `nbformat`, sau đó các test notebook báo thiếu `IPython`. Hai gói đã được khai báo trong extra `test` và cài vào môi trường; chạy lại full suite cho kết quả nêu trên.

## Kiểm tra đã bổ sung

- Body sai kiểu, URL rỗng, URL dài quá giới hạn, URL đúng 4096 ký tự và khoảng trắng đầu/cuối.
- URL hợp lệ/lỗi theo parser, gồm Unicode, IPv4/IPv6, port lỗi và hostname lỗi.
- Model/artifact chưa sẵn sàng, artifact lỗi hoặc metadata không tương thích.
- Lỗi inference/lỗi nội bộ được che chi tiết; kiểm tra không lộ URL nhạy cảm, exception hoặc traceback.
- Chặn DNS/socket trong test xử lý URL để kiểm tra luồng offline.
- So sánh response API với `predict_url` trên cùng artifact tổng hợp. Đây **không phải** parity với CLI hoặc model thật.

## Hạng mục còn chờ

- GitHub Actions đã được cấu hình nhưng chưa có kết quả chạy trên GitHub.
- Chưa đo latency mean/p95 với cấu hình và artifact thật.
- Chưa chạy clean-clone acceptance.
- API–CLI parity với artifact thật còn chờ model artifact được bàn giao.
- Smoke test Flutter → API → model thật là hậu kiểm sau bàn giao PR #19.

## Chạy lại trên máy khác

Các lệnh dưới đây dùng đường dẫn tương đối từ thư mục gốc của repository. Cần Python 3.11 trở lên; để so sánh sát với kết quả ghi nhận, dùng Python 3.13.7. `pyproject.toml` khai báo các dependency kiểm thử, gồm `nbformat` và `ipython`.

### Windows PowerShell

```powershell
# Từ thư mục gốc repository
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -e ".[api,test]" tldextract==5.4.0 idna==3.20
& .\.venv\Scripts\python.exe -m pip check
& .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs tests\test_api.py
& .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider -q -rs
```

### Linux/macOS

```sh
# Từ thư mục gốc repository
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[api,test]' tldextract==5.4.0 idna==3.20
python -m pip check
python -m pytest -p no:cacheprovider -q -rs tests/test_api.py
python -m pytest -p no:cacheprovider -q -rs
```

Các skip do thiếu handoff dữ liệu hoặc không có ca regression vẫn có thể xuất hiện; ghi lại đúng output của môi trường chạy. Để thử backend khi chưa có artifact, không đặt `PHISHGUARD_MODEL_BUNDLE`: theo contract `/health` phải ở trạng thái degraded và `/predict` với URL hợp lệ phải trả 503.
