# Workflow chung

## Nơi làm việc

- Repo: source, notebook, cấu hình, tài liệu và báo cáo nhỏ đã kiểm tra.
- Local là luồng mặc định: mỗi người có Python `.venv`, VS Code/Jupyter và notebook riêng.
- Repo chung: https://github.com/phuctran33/PhishGuardVN.git.
- Mỗi thành viên có thể chọn Colab thay cho local; code/config và quy tắc đánh giá vẫn chung.
- Dataset, bảng lớn và model bàn giao bằng file/thư mục nhóm đã thống nhất;
  có thể gửi bản ZIP, dùng ổ chia sẻ hoặc Drive. Drive không phải yêu cầu bắt buộc.

## Thiết lập local

Mỗi người clone repo, đặt đúng dataset tại data/ (hoặc đặt PHISHGUARD_DATA_DIR),
tạo `.venv` và cài requirements.txt. Trong VS Code chọn kernel/interpreter của
`.venv`; chạy script và notebook bằng cùng môi trường. Không dùng chung thư mục
môi trường ảo giữa các máy. Hướng dẫn lệnh cụ thể có trong README ở root repo.

## Quy ước

1. Mỗi task có người phụ trách, đầu ra và người kiểm tra.
2. Khi có repo, dùng nhánh `week4/data-quality`, `week4/eda`,
   `week4/url-features`, `week4/baseline`; đồng bộ trước khi sửa.
3. Notebook gọi module src; không sao chép parser/extractor vào từng notebook.
4. Chỉ lưu output notebook cần thiết; tránh in toàn bộ dataset.
5. Đổi features/split phải thông báo người dùng đầu ra và ghi vào decisions.md.
6. Ghi phiên bản môi trường sau lần chạy đã được xác nhận; lưu config và seed
   với kết quả. Template hiện chưa khóa phiên bản thư viện.

## Bàn giao và tái chạy

Giữ id và ghi dataset version, quy tắc lọc, parser/feature version, split, ngày tạo.
Metadata không lọt vào X. File model/features/fold bàn giao riêng phải có tên rõ,
người phụ trách và nơi lấy file trong ghi chú bàn giao. Cùng bản dataset không có
nghĩa là cùng đường dẫn tuyệt đối trên tất cả máy; dùng biến môi trường khi cần.

Lấy đúng source/config/data version, cài môi trường, chạy check_setup,
chạy từng bước đã triển khai và đối chiếu số mẫu/metric. Kết quả local lưu tại
data/interim, data/processed, models và reports theo loại file. Sao lưu các file
bị Git bỏ qua bằng cách nhóm đã thống nhất. Nếu dùng Colab, tải kết quả cần giữ
về máy hoặc lưu ra nơi bàn giao trước khi đóng runtime.
