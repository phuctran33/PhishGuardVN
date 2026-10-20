# Kiểm tra khi triển khai

Chưa có test nghiệp vụ vì parser/extractor/ML đang là template.
Khi viết code, ưu tiên các kiểm tra có thể bắt lỗi thật:

- Parser: thiếu scheme, `.com.vn`, IP, `@`, port lỗi, Unicode/Punycode,
  giữ path/query, thương hiệu trong subdomain.
- Features: tính tay trên URL tổng hợp `.example`, phạm vi đếm scheme,
  mẫu số 0, NaN/inf và thứ tự cột.
- Split: domain không giao nhau, đủ hai lớp mỗi fold, id không mất/nhân bản khi join.
- Pipeline: scaler/selector fit trong fold; load artifact cho cùng dự đoán;
  train và predict dùng cùng công thức features.

Không truy cập website từ URL trong dataset để kiểm tra.
