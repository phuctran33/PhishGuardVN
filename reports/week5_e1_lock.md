# Mốc E1 trước khi bắt đầu thí nghiệm tuần 5

Baseline đã merge qua PR #4 vào main ở commit `3e9001c`; commit sửa review `aa42740`. Đối chiếu source với metadata E1 đã lưu: toàn bộ hash khớp. Đây là kiểm tra snapshot đã có, không phải một lần chạy baseline mới.

E1 dùng 12 feature, 3 domain folds, threshold0.5, chọn LR theo mean CV F1 phishing. LR balanced thắng tiêu chí E1 (F1≈0.4831), nhưng FPR CV≈28.94% và official validation có646 FP/1561 benign; không coi đây là model sẵn sàng triển khai. Official test chưa được dự đoán/chấm.

Bảng/hash E1 nằm trong reports/tables/05_e1_lock.json; source/config/notebook04, reports04, model local và metadata được snapshot trước chạy tuần5 và kiểm lại sau. Không retune hay ghi đè E1. Tuần5 chuyển tiêu chí chọn sang AP theo quyết định Phúc và lưu file05 riêng.

Giới hạn FP/FN/source shift xem reports/week4_error_analysis.md. Chốt mốc kỹ thuật này không thay cho review/duyệt Teacher hoặc nghiệm thu tuần5 của cả nhóm.
