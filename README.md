# PhishGuard VN

Đồ án CSC14005 — phát hiện nguy cơ từ URL và nghiên cứu đặc trưng thương hiệu
trong bối cảnh Việt Nam.

**Trạng thái tuần 4: đã có kiểm định dữ liệu, parser/features, EDA/Group CV và baseline Dummy/LR.**
Baseline là kết quả ban đầu; chưa đánh giá official test và chưa chọn mô hình cuối kỳ.
Xem [báo cáo baseline](reports/week4_baseline.md), [phân tích FP/FN và chênh lệch CV–Validation](reports/week4_error_analysis.md) và notebook `04_baseline_ml.ipynb`.

**Mặc định chạy hoàn toàn local** bằng VS Code/Jupyter và môi trường `.venv` riêng.
GitHub dùng để quản lý code; từng thành viên có thể chọn môi trường chạy khác nhau.
Google Colab là tùy chọn, không cần tài khoản Colab hay Google Drive để chạy local.

## Phạm vi tuần 4

- Kiểm định PhishVN, EDA và kiểm tra split/domain.
- Xây parser và URL Features tham khảo schema 21 features của PhishVN.
- Chạy mốc Dummy và baseline Logistic Regression, đánh giá và phân tích lỗi.
- Frontend, backend, QR, Brand Detector và Brand Features từ tuần 5 trở đi.

## Phân công đề xuất

| Thành viên | Phụ trách | File bắt đầu |
| --- | --- | --- |
| Tiết Trọng Khiêm | Chất lượng và chuẩn bị dữ liệu | `notebooks/01_data_quality.ipynb`, `src/phishguard_vn/data.py` |
| Nguyễn Đức Hưng | EDA, split và CV | `notebooks/02_eda_and_splits.ipynb`, `src/phishguard_vn/splits.py` |
| Nguyễn Khang Hy | Parser và URL Features | `notebooks/03_url_features.ipynb`, `src/phishguard_vn/url_parser.py`, `src/phishguard_vn/features.py` |
| Trần Thiên Phúc | Baseline và đánh giá | `notebooks/04_baseline_ml.ipynb`, `src/phishguard_vn/modeling.py`, `src/phishguard_vn/evaluation.py` |

Tên/vai có thể hoán đổi theo thống nhất. Xem
[`docs/project/week4_tasks.md`](docs/project/week4_tasks.md).

## Cấu trúc

```text
PhishGuardVN/
├── configs/baseline.toml          # Cấu hình cố định cho baseline tuần 4
├── data/
│   ├── dataset_url.csv            # PhishVN gốc; giữ nguyên, có sẵn trong repo
│   ├── vn_compphish.csv           # Bảng features tham khảo
│   ├── abuse_type.csv             # Thông tin phụ cho EDA
│   ├── splits/                   # Split chính thức
│   ├── attacks/                  # Chưa dùng ở tuần 4
│   ├── interim/                  # Bảng kiểm định, domain, fold do nhóm tạo
│   └── processed/                # Ma trận features do nhóm tạo
├── notebooks/                    # 01 → 03 → 02 → 04: chuỗi dữ liệu đến baseline
├── src/phishguard_vn/             # Parser, features, CV, modeling, evaluation, reporting
├── scripts/check_setup.py         # Kiểm tra đường dẫn/file cục bộ
├── models/                       # Baseline LR + metadata local, bị Git bỏ qua
├── reports/
│   ├── figures/
│   ├── tables/
│   └── templates/                # Mẫu báo cáo, features, metric và phân tích lỗi
├── docs/
│   ├── dataset_README.md          # README PhishVN gốc
│   ├── datasheet.md               # Tài liệu gốc của tác giả
│   ├── schema.md
│   ├── data_sources.md
│   └── project/                  # Workflow, quyết định và task của nhóm
├── tests/                        # Split/CV và baseline contracts
├── requirements.txt
├── pyproject.toml
├── LICENSE                       # Giấy phép DATASET gốc
├── CITATION.cff                  # Trích dẫn DATASET gốc
└── MANIFEST.txt                  # Checksum bản phát hành PhishVN
```

## Chạy local — luồng chính

### 1. Lấy code và dữ liệu

Thành viên chưa có repo:

```powershell
git clone https://github.com/phuctran33/PhishGuardVN.git
cd PhishGuardVN
```

Dataset PhishVN v3.1.0 gốc đã có trong repo: clone về là có dữ liệu ở `data/`.
Nếu đã có thư mục dự án, cập nhật bằng `git pull --ff-only` rồi mở chính thư mục
đó trong VS Code. Xem [`data/README.md`](data/README.md) để biết các file dữ liệu.

### 2. Tạo môi trường Python riêng

Chọn Python 3.11+; chạy tại root repo. Trên Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/check_setup.py
```

Không cần activate môi trường nếu gọi trực tiếp Python trong `.venv` như trên.
Trên macOS/Linux dùng `.venv/bin/python`.

### 3. Mở notebook trong VS Code hoặc JupyterLab

- VS Code: cài extension Python/Jupyter nếu chưa có, mở notebook được phân công,
  chọn kernel Python của `.venv` trong repo. Dùng cùng interpreter này khi chạy `.py`.
- Hoặc mở JupyterLab tại root repo:

```powershell
.\.venv\Scripts\python.exe -m jupyterlab
```

Notebook tự tìm root repo, đọc dữ liệu ở `data/` và config ở `configs/`.
Chạy notebook theo thứ tự **01 → 03 → 02 → 04**. Mỗi bước tạo artifact cho bước kế tiếp.

### 4. Dữ liệu ở ổ đĩa khác — tùy chọn

Nếu giữ dữ liệu ở `data/` trong repo thì không cần đặt biến nào.
Nếu dữ liệu ở nơi khác, đặt đường dẫn thực trước khi chạy notebook/script:

```powershell
$env:PHISHGUARD_DATA_DIR = "D:\Datasets\PhishVN_v3.1.0_open\data"
.\.venv\Scripts\python.exe scripts/check_setup.py
```

Hoặc trong notebook, trước ô thiết lập đường dẫn:

```python
import os
os.environ["PHISHGUARD_DATA_DIR"] = r"D:\Datasets\PhishVN_v3.1.0_open\data"
```

`PHISHGUARD_ROOT` chỉ cần khi không thể tìm root tự động. Mỗi người đặt đường dẫn
trên máy mình; không ghi cố định đường dẫn cá nhân vào code chung.

### 5. Ghi môi trường đã xác nhận

Dependencies chưa khóa phiên bản ở giai đoạn template. Sau khi cả nhóm xác nhận
môi trường chạy đúng, lưu phiên bản thực dùng để tái lập thí nghiệm:

```powershell
.\.venv\Scripts\python.exe -m pip freeze > requirements-lock.txt
```

Kiểm tra file trước khi đưa vào repo; thay đường dẫn editable của máy cá nhân bằng
`-e .` nếu có. Ghi phiên bản Python và cấu hình cùng kết quả thực nghiệm.

## Google Colab — tùy chọn cho từng thành viên

Nếu một thành viên chọn Colab: clone repo vào runtime, chuyển working directory
vào repo và cài `requirements.txt`. Dataset gốc đã có ở `data/`; chỉ cần đặt
`PHISHGUARD_DATA_DIR` nếu chủ động dùng bản dữ liệu ở nơi khác. Drive là tùy chọn
lưu kết quả. Trước khi đóng runtime, tải kết quả cần giữ về máy hoặc nơi lưu nhóm
đã thống nhất. Code/parser/features và cấu hình dùng chung với luồng local.

Xem [`docs/project/workflow.md`](docs/project/workflow.md) để phối hợp trong nhóm.


## Chạy baseline tuần 4

Sau khi đã chạy 01 → 03 → 02 để tạo handoff CSV:

```powershell
.\.venv\Scripts\python.exe scripts/train_baseline.py
.\.venv\Scripts\python.exe scripts/analyze_baseline_errors.py
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

Hoặc mở `notebooks/04_baseline_ml.ipynb` bằng kernel `.venv` để xem từng bước.
Dummy là mốc tham chiếu. LR thường và LR balanced là hai cấu hình của cùng thuật toán.
Chọn cấu hình bằng F1 phishing trung bình trên Group CV, ngưỡng cố định 0,5;
validation chỉ bổ sung và test chưa được dự đoán. Scaler fit riêng trong train mỗi fold.
Code tự kiểm tra ID, domain, cột đầu vào và rò rỉ val/test trong fold.
Model/metadata nằm tại models/, predictions lớn tại data/interim/, bảng nhỏ và hình ở reports/.
File kết quả sẽ được tái tạo khi chạy lại cùng lệnh; thời gian fit có thể khác giữa các máy.
Ghi chú observation/hypothesis/next_check trong `04_error_examples.csv` được giữ lại;
`04_error_notes.csv` tự lưu ghi chú của ví dụ không còn được chọn ở lần chạy mới.
Môi trường và hash source/handoff của kết quả nằm trong `reports/tables/04_run_metadata.json`.
Để đối chiếu kết quả đã lưu, dùng cùng phiên bản Python/thư viện ghi trong metadata;
chỉ giữ seed giống nhau chưa đủ bảo đảm tái lập giữa các phiên bản scikit-learn.

## Quy tắc dữ liệu và đánh giá

- Baseline bắt đầu với core `gold` + `silver`; để bronze riêng.
- Giữ `id` để nối đúng URL, X, y, split và fold.
- Kiểm tra giao nhau domain đăng ký trước khi tin vào split chính thức.
- Core validation có 24 mẫu phishing trước bước lọc bổ sung. Thiết kế CV theo
  domain trên train và báo cáo rõ giới hạn validation.
- Fit scaler/selector trong phần train từng fold; test dành cho đánh giá cuối.
- Metadata (`source`, `tier`, `split`, `scenario`, `abuse_type`...) dùng kiểm định,
  không làm đầu vào baseline. Loại `is_https` theo lưu ý tác giả.
- 21 features là tập ứng viên, không phải số lượng tối ưu đã xác nhận. Định nghĩa
  công thức, kiểm tra tính đúng và ghi lý do giữ/bỏ từng cột.
- Chỉ phân tích chuỗi URL; parser không tải nội dung website.

## Trước khi đưa lên repo

CSV gốc của PhishVN được quản lý phiên bản cùng code để cả nhóm dùng đúng một bản.
Giữ nguyên byte của dataset và thông tin nguồn; đối chiếu `MANIFEST.txt` khi cần.
`.gitignore` tiếp tục loại dữ liệu trung gian, model, môi trường ảo và cache.
Các file sinh ra được bàn giao riêng theo cách nhóm thống nhất. Không điền số liệu
minh họa vào bảng kết quả thực; chỉ commit kết quả nhỏ đã kiểm tra.

## Ghi nguồn

PhishVN v3.1.0, tác giả Thai Nguyen Vu, DOI `10.17632/b97hxbxtpd.4`.
README gốc tại [`docs/dataset_README.md`](docs/dataset_README.md).
`LICENSE`, `CITATION.cff`, `MANIFEST.txt` và tài liệu dataset gốc được giữ nguyên.
`LICENSE` áp dụng cho dataset; giấy phép code mới của nhóm chưa được lựa chọn.
