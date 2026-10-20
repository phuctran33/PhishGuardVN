# PhishGuard VN

Đồ án CSC14005 — phát hiện nguy cơ từ URL và nghiên cứu đặc trưng thương hiệu
trong bối cảnh Việt Nam.

**Trạng thái: template tuần 4, chưa thực hiện EDA hay huấn luyện mô hình.**
Các hàm nghiệp vụ có `TODO`/`NotImplementedError`; notebook là dàn ý để nhóm điền.

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
├── configs/baseline.toml          # Cấu hình đề xuất, chưa phải kết quả
├── data/
│   ├── dataset_url.csv            # PhishVN gốc; giữ nguyên, không đưa lên Git
│   ├── vn_compphish.csv           # Bảng features tham khảo
│   ├── abuse_type.csv             # Thông tin phụ cho EDA
│   ├── splits/                   # Split chính thức
│   ├── attacks/                  # Chưa dùng ở tuần 4
│   ├── interim/                  # Bảng kiểm định, domain, fold do nhóm tạo
│   └── processed/                # Ma trận features do nhóm tạo
├── notebooks/                    # 4 notebook có dàn ý/TODO
├── src/phishguard_vn/             # Module dùng chung, nghiệp vụ chưa triển khai
├── scripts/check_setup.py         # Kiểm tra đường dẫn/file cục bộ
├── models/                       # Chưa có model
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
├── tests/README.md               # Tình huống cần kiểm tra khi viết code
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

Nếu đã có thư mục dự án, mở chính thư mục đó trong VS Code. Chuẩn bị PhishVN
v3.1.0 theo [`data/README.md`](data/README.md); máy hiện tại đã có dataset.

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
Các ô TODO được thành viên phụ trách triển khai; chạy template chưa tạo ra EDA/model.

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
vào repo, cài `requirements.txt` rồi chuẩn bị cùng bản dataset ở `data/` hoặc đặt
`PHISHGUARD_DATA_DIR`. Có thể tải dataset từ máy lên runtime; Drive là một lựa chọn
lưu trữ thêm. Trước khi đóng runtime, tải kết quả cần giữ về máy hoặc nơi lưu nhóm
đã thống nhất. Code/parser/features và cấu hình dùng chung với luồng local.

Xem [`docs/project/workflow.md`](docs/project/workflow.md) để phối hợp trong nhóm.

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

`.gitignore` loại CSV gốc, dữ liệu trung gian, model, môi trường ảo và cache.
File vẫn giữ trên máy; thành viên khác lấy dataset theo hướng dẫn. Không điền
số liệu minh họa vào bảng kết quả thực. Chỉ commit code/tài liệu/kết quả nhỏ đã
kiểm tra; dataset và model được bàn giao riêng theo cách nhóm thống nhất.

## Ghi nguồn

PhishVN v3.1.0, tác giả Thai Nguyen Vu, DOI `10.17632/b97hxbxtpd.4`.
README gốc tại [`docs/dataset_README.md`](docs/dataset_README.md).
`LICENSE`, `CITATION.cff`, `MANIFEST.txt` và tài liệu dataset gốc được giữ nguyên.
`LICENSE` áp dụng cho dataset; giấy phép code mới của nhóm chưa được lựa chọn.
