# Nhật ký quyết định

Chưa có quyết định thực nghiệm được xác nhận. Điền sau khi họp và kiểm tra.

| Ngày | Quyết định | Căn cứ/file kết quả | Người xác nhận | Ảnh hưởng/việc chạy lại |
| --- | --- | --- | --- | --- |
| TODO | TODO | TODO | TODO | TODO |

Cần chốt: core/bronze; domain giao nhau; CV; công thức features; cột hằng;
định nghĩa PR-AUC; cấu hình baseline và môi trường dùng chung.


## Quyết định phần Phúc trước chạy tuần5

| Ngày | Quyết định | Căn cứ | Người xác nhận | Ảnh hưởng |
|---|---|---|---|---|
| 01/11/2026 | AP (average precision) làm primary cho chọn cấu hình trong train và so sánh family tuần5; báo F1/Recall/FPR kèm, threshold0.5 cố định | Phúc chọn AP làm chính trong hội thoại trước khi triển khai; docs/project/week5_protocol.md | Phúc | Áp dụng mốc lexical12; không thay winner/tiêu chí E1. Brand ablation/Teacher final chờ Hy và nhóm review. |

Đây là xác nhận của Phúc cho phần thực nghiệm được giao, chưa ghi thay quyết định nghiệm thu của cả nhóm.


## Đơn giản hóa phần ML của Phúc — 02/11/2026

Phúc yêu cầu code dễ đọc và đủ phát triển sau này. Notebook là nguồn train chính, khai báomodel và gọi fit/predict trực tiếp; GridSearchCV thay search tựviết. V2 giữ AP/outer3+inner2groupCV, bỏ SVMcalibration: dùngdecision_function đểchấmAP vàpredict đểra nhãn. Đây là giao thức mới; output05_readable riêng, v1/E1giữlịch sử. Brand và Teacher chưachốt. Các module nângcao cũ không phải đườnghọcchính.
