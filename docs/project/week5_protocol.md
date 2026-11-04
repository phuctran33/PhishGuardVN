> LỊCH SỬ V1: giao thức nested/calibrated dưới đây giữ để đối chiếu. Bản chạy chính v2 và thay đổi SVM xem reports/week5_readable.md.

# Tuần 5 — giao thức thí nghiệm phần Phúc, mốc 12 feature

Ngày đăng ký: 01/11/2026. Phúc đã chọn **AP (average precision) làm tiêu chí chính** trong hội thoại trước khi chạy tuần 5. Đây là quyết định cho phần thực nghiệm Phúc; chưa thay cho xác nhận nghiệm thu của cả nhóm. Thí nghiệm E1 và tiêu chí F1 cũ được giữ nguyên.

## Phạm vi

- Dùng đúng 12 lexical features, cùng handoff của Khiêm/Hy/Hưng, cùng 3 outer domain folds của E1.
- LR thường và balanced giữ cấu hình C=1, max_iter=2000 làm mốc đối chứng.
- SVM RBF, MLP nhỏ và HistGradientBoosting có 2 cấu hình định trước mỗi họ (xem configs/e2_models.toml).
- Không có brand features giả, chưa có đối chứng 12 vs 12+brand, chưa chọn Teacher cuối cùng. Các mục đó chờ Hy và review chất lượng/trade-off của nhóm.

## Chọn và chấm

1. Mỗi outer fold: giữ nguyên phần chấm; chỉ từ phần fitting còn lại tạo 2 inner StratifiedGroupKFold, seed42, ID được sort. Không domain nào thuộc cả hai phía một split.
2. Mỗi cấu hình được fit và chấm AP ở cả 2 inner folds. Chọn mean inner AP cao nhất; hòa chọn candidate_id tăng dần. Cấu hình có lỗi fit/cảnh báo không hội tụ không được thắng. Nếu không còn cấu hình hợp lệ thì dừng và ghi lỗi, không tự mở rộng search.
3. Fit cấu hình thắng trên toàn outer fitting partition, chấm đúng outer fold một lần. LR đối chứng một cấu hình không cần tuning.
4. Xếp hạng họ mô hình bằng mean outer AP; hòa dùng mean F1 rồi FPR thấp hơn, cuối cùng tên mô hình. Mọi outer fit và full-train fit của ứng viên phải hội tụ. Đây là lựa chọn họ mô hình từ CV, không phải đánh giá cuối độc lập sau lựa chọn.
5. Sau CV, tune cấu hình cuối của từng họ bằng 2 inner group folds trên toàn official train, rồi fit toàn train. Official validation chỉ chấm bổ sung sau lựa chọn; test không fit/predict/score.

## Tiền xử lý và score

- LR/MLP dùng StandardScaler nằm trong pipeline và fit riêng theo fitting partition.
- SVM dùng SVC(probability=False) trong pipeline scaler+SVC, bọc CalibratedClassifierCV(sigmoid, ensemble=False, n_jobs=1). Hai calibration folds theo domain được tạo lại bên trong mỗi fitting partition. Scaler nằm **trong base pipeline**, để không nhìn calibration holdout. Calibration tạo OOF margins trong fitting, sau đó base model được refit toàn fitting.
- HistGB không dùng scaler. MLP và HistGB đặt early_stopping=False để không sinh validation split ngẫu nhiên không theo domain. MLP được phép dừng theo training loss; vẫn ghi cảnh báo nếu hết budget chưa hội tụ.
- Ngưỡng 0,5 cố định, không tune theo validation. Cùng ngưỡng số không có nghĩa cùng FPR/điểm vận hành giữa các họ. SVM có sigmoid calibration nội bộ theo group; không gọi mọi score là xác suất rủi ro thực tế đã hiệu chuẩn.
- Metrics dùng cùng summarize_predictions của E1: AP=average_precision, phishing=1; báo precision/recall/F1/FPR và số TP/FP/FN/TN. Báo mean/std theo fold riêng với pooled OOF.
- Hạn chế CPU 1 thread cho phép đo tuần này, không chạy search song song lồng nhau. Lưu toàn bộ config, ID/hash split, fit status và thời gian.

## Nguồn dữ liệu và tính tái lập

Giữ nguyên các file E1; tuần 5 ghi output tên 05*. Model/predictions ở models/ và data/interim/ bị Git bỏ qua, các bảng/báo cáo nhỏ trong reports/ được review. Metadata ghi source/config/input/artifact hashes và phiên bản thư viện, HEAD nền và trạng thái source lúc chạy. Không tự sửa nhãn hoặc official split.

Source/label confounding chưa được loại bỏ chỉ nhờ Group CV. Validation chỉ có 24 phishing theo handoff hiện tại; đọc score cùng support và phân bố nguồn. Pilot ngoài và robustness do Khiêm/Hưng phụ trách sẽ bổ sung bằng chứng.

## Bàn giao cho Hy/Hưng và việc còn chờ

- Hưng nhận 05_cv_predictions.csv và 05_validation_predictions.csv (id/model/fold/true_label/predicted_label/score) để audit lỗi theo nguồn/tier/kiểu URL; không đưa metadata đó vào X.
- Hy cần bàn giao feature dictionary, công thức/dtype/order, version/hash reference, ID coverage và invalid policy của brand features trước khi thêm schema E2 mới. Runner hiện chỉ chấp nhận lexical_12 và sẽ từ chối cột brand/metadata, không tự điền feature chưa làm bằng0.
- Đối chứng brand phải giữ same eligible samples/folds; nếu coverage khác phải ghi rõ và đối chứng trên tập chung. Chỉ mở schema sau review contract, không âm thầm đổi 12 cột E1.
- Chọn tối đa 2 Teacher sau khi xem chất lượng, FPR–Recall trade-off, tài nguyên và brand-aware comparison. Xếp hạng lexical tuần này chỉ là kết quả tạm thời; chưa có KD/mobile.
