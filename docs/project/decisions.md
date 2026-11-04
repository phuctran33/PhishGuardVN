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


## 04/11/2026 — E2 ablation readable, producer handoff

Tích hợp Hy PR #5 main 0054a1b vào nhánh Phúc; E2 trainval 20 features, reference draft. Notebook E2 ablation dùng cùng samples/folds/grid/seed như notebook05; AP inner/outer, không threshold tuning, SVM margin/estimator.predict. Không đổi E1 đã khóa.
Quy tắc shortlist khai báo trước khi chạy: mỗi họ lấy feature set mean AP cao nhất, tie F1/FPR/candidate; tối đa hai họ. Kết quả E2 MLP/HistGB; CV tăng nhưng Validation AP giảm, ghi giới hạn thay vì sửa theo Validation. Uncertainty là paired-fold descriptive mean/std/min/max, không giả là CI.
Xuất predictions + shared training partitions dạng CSV nén và metadata hiện có để Hưng audit độc lập; code/reference nằm trong repo, model giữ local. Không ép margin qua probability-only adapter; không triển khai KD/mobile hay thêm registry/audit framework. Producer verification không thay human review của Hưng.


## 04/11/2026 — Bàn giao tối giản qua repo

Đưa đúng ba bảng `06_oof_predictions.csv.gz`, `06_validation_predictions.csv.gz`, `06_training_partitions.csv.gz` vào reports/tables, tổng khoảng 5,4 MiB. Hưng pull rồi đọc bằng pandas, không cần giải nén hoặc train lại trước khi audit. Bỏ thư mục handoffs, ZIP, delivery manifest và bản sao code/model/reference; dùng metadata/bảng kết quả đã có. Notebook trực tiếp xuất ba file sau mỗi lần chạy; hướng dẫn duy nhất ở docs/week5_phuc_handoff.md. Dữ liệu gốc của lần chạy hiện có được nén nguyên byte, các cell huấn luyện và model không đổi.
