# Tuần 8 · Tra cứu ca phishing lịch sử tương tự

Issue [#36](https://github.com/phuctran33/PhishGuardVN/issues/36) · Trần Thiên Phúc

## Kết quả bàn giao

`POST /similar-cases` khớp schema Flutter trong PR [#40](https://github.com/phuctran33/PhishGuardVN/pull/40). Người dùng có thể tìm tối đa 5 ca lịch sử theo hostname, xem đoạn giống và nguồn ghi nhận. Điểm cosine đo độ giống chuỗi. Nhãn phân loại trên Web lấy từ `/predict`.

Phạm vi bản đầu là **hostname**. Trong nhóm ca được chọn có 7 URL mang path và 0 URL mang query. Chuẩn hóa host bằng parser chung, dùng ASCII/Punycode với IDN. Userinfo, port, path, query và fragment đứng ngoài chỉ mục và chuỗi hiển thị. Kết quả hiển thị bằng text với scheme `hxxp` hoặc `hxxps` và dấu chấm `[.]`.

## Corpus và tiêu chí tra cứu

| Mục | Số liệu |
|---|---:|
| Phishing Gold/Silver từ Train | 2.076 |
| Không parse được hoặc không hỗ trợ | 2 |
| Hostname trùng sau chuẩn hóa | 2 |
| Ca trong danh mục, tất cả từ `tinnhiemmang` | **2.072** |

Giữ một ca cho mỗi hostname, ưu tiên Gold rồi case ID để tái lập. Manifest nằm trong [tệp corpus](../src/phishguard_vn/resources/similar_cases_v1.json). SHA-256 của Train đầu vào là `568e788eda4bdf62531adcddd093373ef6a1e97feec1354063ae337325367b61`. SHA-256 của corpus sinh với LF là `4b7ef53e94fe874349e352db012721a798d4c26bc607df74cfb2194bf9f680ee`.

FastAPI nạp corpus và fit TF-IDF ký tự 3–5 gram một lần lúc khởi động. Vector chuẩn L2 cho phép dùng tích vô hướng để tính cosine. Ngưỡng là **0,40**, kèm ít nhất một đoạn giống có từ bốn ký tự chữ/số trước nhãn DNS cuối. Điều kiện thứ hai loại ca chủ yếu giống đuôi ngắn như `88.com`. Sắp theo cosine giảm dần, dùng case ID khi hòa điểm, bỏ bản ghi trùng hostname của truy vấn. Corpus nằm trong Python package và thuộc thư mục `src` mà Dockerfile của PR #40 đưa vào ảnh demo.

Nguồn dữ liệu là PhishVN 3.1.0 của Thai Nguyen Vu, DOI `10.17632/b97hxbxtpd.4`, CC BY 4.0. Bản dẫn xuất lọc Train, nhóm theo hostname và bỏ các thành phần còn lại của URL. [Trích dẫn](../CITATION.cff) · [Giấy phép](../LICENSE)

## Hợp đồng Web và fixtures QA

- Request là `POST /similar-cases` với `{"url":"..."}`. Trả HTTP 200 và `status: "ok"` kèm 1–5 ca, hoặc `{"status":"empty","cases":[]}`.
- Mỗi ca có `case_id`, `display_url`, `source`, `cosine_similarity` và `highlights`. `{start,end}` là offset Unicode code point trên chuỗi hiển thị. `start` tính vào đoạn, `end` nằm ngay sau đoạn. Các đoạn có thứ tự và không chồng nhau.
- HTTP 422 dùng lỗi validation chung. HTTP 503 với `SIMILAR_CASES_UNAVAILABLE` báo corpus không sẵn sàng. Tra cứu chạy độc lập với độ sẵn sàng của Teacher.
- [Response mẫu sinh từ API bằng corpus tổng hợp](../tests/fixtures/similar_cases_v1_example.json) · [Kiểm thử](../tests/test_similar_cases.py)

## Kiểm trên dữ liệu phát triển

Chấm 1.585 URL Gold/Silver Validation ngoài hostname Train đã lập chỉ mục. Benchmark trên Windows, CPython 3.11, sau 10 lượt làm nóng. p50/p95 đo từ URL đầu vào đến kết quả trong hàm tra cứu, gồm parse, TF-IDF, xếp hạng và tô sáng.

| Nhãn của truy vấn | Số truy vấn | Có ca tương tự | Rỗng |
|---|---:|---:|---:|
| Phishing | 24 | **4** | 20 |
| Benign | 1.561 | **139** | 1.422 |

Thời gian tra cứu **p50 0,628 ms**, **p95 0,945 ms** và nạp danh mục khoảng **107 ms** trong lượt đo. Bảng đo độ phủ tra cứu theo nhãn truy vấn. Official Test đứng ngoài phép đo.

- Ca Validation `ee4a3a51` có ứng viên Train `18060575`, cosine **0,663**, trùng đoạn `my[.]exness`. Đây là ví dụ chuỗi tên giống để người dùng đối chiếu.
- Ca benign Validation `53aea21e` có ứng viên Train `67bbd2da`, cosine **0,509**, trùng từ `sukien`. Hai tên miền có thể gần nhau vì cùng một từ phổ biến. UI cần giữ điểm tương tự tách khỏi nhãn phân loại.
- Ca tổng hợp `p88[.]com` với `k88[.]com` bị lọc vì chỉ giống đoạn ngắn và đuôi DNS. Các URL có cùng hostname và khác path có kết quả tra cứu giống nhau.

## Cách chạy lại

Từ checkout có Python 3.11, dùng môi trường API của dự án.

```powershell
python -m pip install -r requirements-teacher.txt -e ".[api,test]"
python scripts/build_similar_cases.py
python scripts/evaluate_similar_cases.py
python -m pytest -q tests/test_similar_cases.py tests/test_api.py tests/test_api_teacher.py tests/test_url_inspection.py --teacher-root . --teacher-api
python -m uvicorn phishguard_vn.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Lượt hồi quy trên nhánh này có **81 test đạt**, gồm Teacher thật và URL Inspection. Hưng có thể nối endpoint thật vào PR #40 theo contract và fixture. Khiêm có thể kiểm trạng thái có ca, rỗng và lỗi corpus từ cùng SHA.

Bản ghép thử với PR #40 tại `4ef609e` có **114 test backend đạt**. Wheel từ bản ghép chứa corpus tra cứu và manifest danh mục thương hiệu.
