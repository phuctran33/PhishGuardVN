# Dữ liệu

CSV gốc giữ nguyên trên máy, được `.gitignore` bỏ qua để repo chứa code/tài liệu.
Thành viên khác lấy đúng PhishVN v3.1.0 từ bản ZIP/thư mục dùng chung hoặc nguồn
đã được nhóm xác nhận, rồi giải nén/sao chép đúng vị trí trên máy mình. Không cần Drive.

```text
data/
  dataset_url.csv
  vn_compphish.csv
  abuse_type.csv
  splits/url_train.csv
  splits/url_val.csv
  splits/url_test.csv
  attacks/p3_paraphrase.csv
  attacks/p3_paraphrase_band.csv
  interim/       # Bảng kiểm định, domain, fold_id do nhóm tạo
  processed/     # Features sau khi extractor được triển khai
```

Chạy `python scripts/check_setup.py` để kiểm tra sự có mặt của các file.
Chất lượng dữ liệu và domain leakage được kiểm tra trong notebook khi triển khai.

Nếu dữ liệu ở nơi khác, đặt `PHISHGUARD_DATA_DIR` tới thư mục chứa
`dataset_url.csv`, `splits/`...; module paths.py dùng nơi đó cho đầu vào.
Kết quả xử lý mặc định vẫn lưu dưới repo; các file bị Git bỏ qua cần được sao lưu
và bàn giao riêng. Nếu chọn Colab, tải chúng về trước khi đóng runtime.

Bảng chính, features và split có phần trùng nhau, không nối dọc thành dataset lớn hơn.
`abuse_type.csv` dùng phân tích lớp dương, không làm X. Không sửa/ghi đè file nguồn.
EDA không yêu cầu mở các URL. Đối chiếu bản phát hành bằng `MANIFEST.txt`;
trích nguồn bằng `CITATION.cff`.
