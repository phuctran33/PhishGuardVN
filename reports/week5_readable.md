# Phúc — ML tuần 5, bản dễ đọc v2

Ngày chỉnh luồng: 02/11/2026. Notebook chính: `notebooks/05_advanced_models.ipynb`. Mục tiêu là đọc từ trên xuống và nhìn thấy lời gọi scikit-learn trực tiếp, đồng thời giữ đánh giá hợp lệ và đường dùng lại model cho web.

## Cách học từng phần

| Phần notebook | Học điều gì? |
|---|---|
| 1–2 | Đường dẫn, X/y, ID, domain và ba folds; metadata đứng ngoài X |
| 3 | Khai báo từng model, scaler và lưới tham số |
| 4 | Một ví dụ LR: `.fit()` → `.predict()` → F1/AP |
| 5 | Một hàm metrics ngắn, dùng trực tiếp scikit-learn |
| 6–7 | Đánh giá ba outer folds, chọn cấu hình bên trong train bằng GridSearchCV, tổng hợp AP |
| 8 | Chọn cấu hình cuối trên toàn train, chấm validation bổ sung |
| 9 | Biểu đồ và 12 ví dụ lỗi thật, trải ba folds |
| 10–11 | Lưu bundle, load và predict URL mới |

Nếu bạn thay một tham số trong phần 3, Run All sẽ chạy lại và lưu kết quả v2. Nhận xét thủ công trong tài liệu này cần cập nhật khi đổi data/grid; không có code tự suy diễn nhận xét mới. Không dùng validation/test để quyết định tham số.

## Giao thức đủ cho thí nghiệm có tuning

- Dữ liệu hiện tại: 13.078 train (2.074 phishing), 1.585 validation (24 phishing), 12 lexical features.
- Cùng 3 outer domain folds của Hưng. Inner2 group folds chỉ trên outer fitting để chọn tham số theo AP; pipeline scaler được fit lại trong từng lượt.
- Hai LR cố định C=1 làm đối chứng; SVM thử C=0.5/2; MLP thử 32 hoặc 32–16; HistGB thử 7/15 leaves. Lưới kế thừa v1, không mở rộng theo kết quả validation.
- Model winner dựa mean outer AP, hòa F1 rồi FPR thấp hơn và tên. Đây là lựa chọn từ CV, không phải đánh giá cuối độc lập của winner.
- MLP/HistGB tắt validation early stopping ngẫu nhiên. Cảnh báo không hội tụ chuyển thành lỗi; không công bố fit chưa hội tụ như đã xong.
- Sau CV, GridSearchCV chọn lại cấu hình trên toàn train, refit toàn train. Validation chỉ báo cáo bổ sung. Official test không tạo X/y riêng, không fit/predict/score; chỉ metadata/domain đã được kiểm tra.

## Thay đổi quan trọng so với v1

V1 có ba tầng outer/inner/SVM calibration. V2 giữ outer và inner, dùng GridSearchCV có sẵn thay search tự viết và bỏ calibration SVM.

SVM: nhãn từ `predict`, score từ `decision_function`, ranh giới mặc định margin0. AP dùng được score này. LR/MLP/HistGB: nhãn từ `predict`, score từ `predict_proba` lớp1. Score SVM không phải probability; không đưa vào bộ audit cũ đòi score [0,1] / threshold 0.5 mà chưa thống nhất adapter/giao thức.

Vì đổi quy tắc score/decision của SVM, kết quả v2 được ghi riêng, không gọi là tái lập hoàn toàn v1. Các bảng/model E1 và v1 giữ nguyên. Đổi cell chú thích hoặc output notebook không làm model bị khóa bởi fingerprint code báo cáo; metadata ghi một hash các code cells để truy vết.

## Kết quả đã chạy

Xem `tables/05_readable_comparison.csv`, `05_readable_validation.csv` và output notebook. AP là average precision. Summary là mean/std từng fold; PR curve OOF gộp chỉ minh họa, không thay tiêu chí chọn. Các score gộp đến từ nhiều model theo fold và có thể khác thang, đặc biệt SVM margin.

Lần chạy đầu v2: MLP mean AP≈0.6992, HistGB≈0.6979, SVM≈0.6426, LR≈0.5942, LRbalanced≈0.5577. MLP chỉ hơn HistGB khoảng0.0013, chưa kết luận thắng vượt trội. HistGB F1≈0.6066 và FPR≈2.01%; MLP F1≈0.5989 và FPR≈2.32%. LRbalanced recall cao hơn nhưng FPR≈28.94%. Chưa chốt Teacher.

Validation có ít phishing, khác nguồn train: MLP AP≈0.4314/F1≈0.3288, HistGB AP≈0.4338/F1≈0.4063. Không dùng các điểm này để đổi winner hoặc threshold. Các kết quả vẫn chịu source-label confounding của dataset.

## Đọc lỗi, quan sát và giả thuyết

`05_readable_errors.csv` là 12 ví dụ thực tế (tối đa 2 FP / 2 FN mỗi fold) của MLP, không phải mẫu ngẫu nhiên hay tần suất nguyên nhân toàn bộ. Nhãn/nguồn/tier lấy từ dataset. Không truy cập website hay đổi nhãn vì model khác đáp án.

- FN `kokatrade[.]com` fold 0 score≈0.1747, `mrhmfund[.]com`≈0.1837: hostname đơn giản vẫn mang nhãn phishing từ nguồn tinnhiemmang/gold. Giả thuyết: feature đếm không biểu diễn nội dung/ý nghĩa URL; cần đối chiếu feature và nhãn gốc trước khi kết luận.
- FN `b1dv[.]xyz` fold 1 score≈0.2042: có chữ số1 trong chuỗi dễ gợi tên gần giống, nhưng bộ12 feature không biểu diễn độ giống thương hiệu. Đây là giả thuyết cho brand ablation sau, không xác minh website giả mạo.
- FP `https://www[.]binhthuan[.]dcs[.]vn` fold 1 score≈0.5661: benign từ tinnhiem_org/gold có nhiều cấp hostname; cần xem các feature subdomain/dot trong nhóm FP. Không kết luận chỉ số cấp domain là nguyên nhân duy nhất.
- FP `pos365[.]vn`≈0.5969, `24hstore[.]vn`≈0.5600: benign có chữ số vẫn bị cảnh báo. Giả thuyết các dấu hiệu hình thức giao nhau với phishing; cần so nhóm train tương tự.
- FP `h-chan[.]me` fold 2≈0.8053 cho thấy model có thể tự tin sai. Score không thay cho bằng chứng trạng thái website.

Bước kiểm tra tiếp: cùng Hưng đọc lỗi theo nguồn và dạng URL; cùng Khiêm kiểm tra độ tin cậy nhãn; sau khi Hy bàn giao mới chạy đối chứng brand trên same samples/folds.

## File cần biết

- Notebook là code train chính; `scripts/train_week5.py` chỉ chạy và lưu chính notebook đó bằng Python hiện tại.
- `src/phishguard_vn/prediction.py`: hàm ngắn dùng lại cho API; URL → extractor của Hy → đúng feature order → model đã học.
- `scripts/predict_week5.py`: gọi hàm predict từ terminal, có `--model` để chọn model trong bundle.
- `models/week5_readable_models.joblib`: models/selected_model/feature_names/score_kinds/protocol. Không chứa một model dùng chung extractor khác lúc train.
- `tables/05_readable_metadata.json`: seed/cáchchia/parameters/libraryversions/input hashes/codehash/modelhash. Không ghi một bộ hash mọi file trong repo làm điều kiện chạy.

## Phát triển tiếp có kiểm soát

Model definitions, grids và FEATURES đều ở đầu notebook. Khi thêm model, khai báo trực tiếp, thêm grid nhỏ và quy tắc score tương ứng. Không xây factory/plugin/runner tổng quát trước khi cần.

Khi thêm brand: cần feature matrix/dictionary/reference version đã thống nhất. Đổi FEATURE_FILE và FEATURES, kiểm coverage cùng ID/folds, nối đúng extractor trong prediction.py trước khi dùng model mới. Không điền brand chưa có bằng 0 hoặc dùng metadata nhưsource làm feature. Khi deploy, app chỉ load bundle và gọi predict, không chạy notebook hay fit lại.

E1 và v1 nâng cao được giữ để đối chiếu. Hướng KD/mobile và đo tài nguyên chi tiết là phần mở rộng sau khi nhóm hiểu mô hình và hoàn thành web/API theo tiêu chí môn học.


## Kiểm chứng lần sửa v2

- Toàn bộ tests: **111 passed**, gồm 7 tests đọc/chạy trực tiếp các code cells v2; không tạo implementation train thứhai để test.
- Notebook chạy đủ11code cells, không có error output. CLI dùng chính notebook, kernel được đóng sau khi chạy; CLI predict SVM hoạt động khi stdout Windows mặc định cp1252.
- AP/F1/confusion được tính lại độc lập từ 65.390 dòng OOF; không có officialtest ID trong predictions. Codecell hash và modelhash khớp metadata.
- Snapshot E1 giữ nguyên. Bảng/hình/model v1 vẫn nguyênbyte; ZIP giữ đúng code v1 và hash source gốc.
- Bản sao sạch v2 không có model/output, dùng cùng bốn handoff đã kiểm chứng và cùng môi trường: notebook/CLI train lại cho summary/validation khớp sai số 1e-10. Không coi đây là kiểm chứng qua mọi phiên bản thư viện.

Các cấu hình LR/MLP/HistGB giữ nguyên kết quả tương ứng ở lần chạy này; SVM khác quy tắc score/nhãn do bỏ calibration và dùngpredict/margin. Không áp số benchmark v1 cho v2.
