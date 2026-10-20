# Tuần 4 — phân công và bàn giao

Phạm vi: kiểm định, EDA, preprocessing, baseline ML.
Frontend/backend và các chức năng ứng dụng từ tuần 5 trở đi.
Ngày 1 là buổi họp khởi động, nhóm điền ngày lịch thực tế.

| Thành viên | Việc chính | Bàn giao |
| --- | --- | --- |
| Khiêm | Kiểm kê, missing/trùng/xung đột, core/bronze, ý nghĩa nhãn | Ngày 2: dữ liệu đầu vào; cuối tuần: notebook chất lượng và quy tắc lọc |
| Hưng | EDA, domain/split, CV | Ngày 3: quy tắc/fold; cuối tuần: biểu đồ và nhận xét |
| Hy | Parser/domain, features tham khảo schema 21 cột | Ngày 2: domain; Ngày 4: X theo id; cuối tuần: module và định nghĩa |
| Phúc | Dummy/LR, metric, lỗi, lưu pipeline và predict local | Ngày 5: baseline đầu; cuối tuần: kết quả, artifact và hướng dẫn |

## Phụ thuộc

1. Khiêm cung cấp bảng chung; Hy giữ id khi parse/extract.
2. Hy cung cấp domain cho Hưng kiểm định split và tạo fold.
3. Hy đưa X, Hưng đưa fold_id, Khiêm đưa y/split cho Phúc.
4. Nối theo id; không ghép theo vị trí sau khi lọc/sắp xếp khác nhau.
5. Hưng bổ sung EDA features sau khi có X; đổi công thức phải ghi phiên bản.

## Nghiệm thu

- Notebook chất lượng/EDA tái chạy được và có nhận xét có căn cứ.
- Dữ liệu có truy vết; domain/fold được kiểm định.
- Features có công thức, căn cứ, lý do giữ/bỏ.
- Có Dummy/LR và metric CV/validation; test dành cho cuối kỳ.
- Pipeline load được; predict local dùng cùng extractor và thứ tự cột.
- Tuần 4 chưa kết luận mô hình tốt nhất của toàn đồ án.
