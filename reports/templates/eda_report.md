# EDA và split — Nguyễn Đức Hưng

Trạng thái: đã chạy trên CSV local; đây là kết quả EDA/integrity audit, không phải metric mô hình.
Notebook: `notebooks/02_eda_and_splits.ipynb`, giữ 12 cell và các section template.

## Dữ liệu và khả năng tái lập

- PhishVN v3.1.0: dữ liệu gốc 53,116 URL; core Gold/Silver 18,997 URL, gồm 16,410 benign và 2,587 phishing.
- Parser/features/dictionary của Hy: commit `65b1054bbc014bb2e434d722acb12073608220b4` (PR #2 đã merge); tldextract 5.4.0, PSL snapshot đóng gói, private suffix=False, IDNA 3.20.
- Local HEAD và origin/main hiện ở `65b1054`. Các CSV được tái tạo bằng nguyên notebook 03 từ snapshot bất biến của đúng commit này; parser/features/dictionary local đã đối chiếu và khớp cùng commit. Notebook 02 đọc dictionary local chính thức, không sửa mã của Hy.
- Python 3.14.0, pandas 3.1.0, NumPy 2.5.4, scikit-learn 1.9.1, matplotlib 3.11.2.
- Khiêm: core được đối chiếu với `prepare_core()` theo ID, mọi cột/giá trị khớp. Không thay dataset, nhãn hoặc official splits.
- Run All bằng kernel mới trong `.venv`; unit/integration tests: **49 PASS**. Test integration có thể skip trên clone sạch nếu chưa tạo các CSV local bị Git bỏ qua.

## Phát hiện chính

| Phân tích | Bằng chứng thực tế | Hàm ý đối với baseline và giới hạn |
| --- | --- | --- |
| 1. Quần thể gốc và core khác nhau | Phishing original 69.11%; core 13.62%; loại 34,119 bronze, toàn bộ phishing trong corpus này | Báo cáo subset và số lớp; không so sánh accuracy/PR-AUC máy móc giữa các prevalence |
| 2. Validation ít positive | Core val 24/1,585 phishing (1.51%); Gold val 0 phishing; một positive đổi recall 4.17 điểm phần trăm | Validation chỉ bổ sung; recall/ROC-AUC Gold-only không xác định; precision phụ thuộc predicted-positive |
| 3. Domain audit và phạm vi chưa xác định | 0 domain giao nhau ở cả ba cặp split trên 18,995 URL đã resolve; 2 unresolved đều là train phishing | Không coi missing là một domain chung, không khẳng định đã kiểm tra được mọi URL/campaign |
| 4. Source và ngày sự kiện không đồng đều | Core 5/5 nguồn single-label; tinnhiemmang chiếm 15.87% train nhưng 1.51% val; collected_at phủ 100% phishing và 12.35% benign core, 0 ngày invalid | Source-label confounding là quan sát, chưa chứng minh model shortcut; không dùng scraped_at thay ngày thiếu hoặc kết luận temporal split sai từ khoảng ngày |
| 5. Group CV thật cân bằng ở seed cố định | 13,078 URL, 8,835 domain; folds 4,359/4,359/4,360 URL, 691/691/692 phishing; chênh prevalence 0.0193 điểm phần trăm | Giữ seed 42; không tối ưu seed/nhãn. Group CV không tự tạo temporal holdout |
| 6. Official X có cột hằng và thưa | 12 features; train 13,078 dòng, NaN/Inf=0; is_ip và under_cnt hằng 0; slash_cnt/path_len cùng 0 ở 99.74% mẫu | Giữ schema bàn giao; nếu dùng selector thì fit trong fold. Không xem IQR=0 là bằng chứng mọi giá trị khác 0 đều lỗi |
| 7. Redundancy và phân bố cần diễn giải thận trọng | Spearman slash_cnt/path_len≈1; url_len/letter_cnt≈0.987; dom_len median benign/phishing=14/11; entropy≈3.324/3.306, IQR chồng lấn | Không suy từ correlation sang nhân quả hoặc tự bỏ cột; khác biệt nhãn còn chịu source confounding |
| 8. Representation sơ bộ khác official X | 1,659 benign core train URL của tinnhiem_org có url_len cũ tính cả scheme; official X bỏ scheme. IQR pooled official url_len đánh dấu 39 URL, chưa xóa/cap | Không trộn quantile giữa hai representation hoặc quy kết thành lỗi join. Whisker boxplot là IQR riêng lớp, khác ngưỡng pooled train |

## Split và domain

Nối `core_gold_silver.csv` với `03_registrable_domains.csv` theo ID, `validate="one_to_one"`; đủ 18,997 core IDs.
Domain hợp lệ: train 8,835, val 1,486, test 1,956 domain duy nhất.

| Cặp split | Domain chung | URL ảnh hưởng A | URL ảnh hưởng B |
| --- | ---: | ---: | ---: |
| train / val | 0 | 0 | 0 |
| train / test | 0 | 0 | 0 |
| val / test | 0 | 0 | 0 |

Hai URL chưa resolve không bị xóa khỏi core hoặc đổi split. Chúng không vào X của Hy và không có fold_id:

| ID | URL đã vô hiệu hóa | Split | Nhãn | Lý do |
| --- | --- | --- | --- | --- |
| `74648118-c397-5d04-ab64-9c2973953892` | `vpbank[.]com[.]vn-uz[.]infor` | train | phishing | unresolved_domain |
| `27984223-c2e3-5068-a777-02f4becd0d10` | `techcombank[.]com-ut[.]xvz` | train | phishing | unresolved_domain |

## Group CV thật

Chạy `make_group_folds()` hiện có trên Gold/Silver official train, loại riêng 2 unresolved có báo cáo.
Không thay thuật toán; `StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42)`.
Mỗi ID xuất hiện đúng một lần, mỗi domain nằm trọn trong một validation fold, train complement không giao domain, hai lớp đủ ở cả hai phía.

| Fold | URL validation | Domain validation | Benign | Phishing | Phishing prevalence |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 4,359 | 2,938 | 3,668 | 691 | 15.8523% |
| 1 | 4,359 | 2,947 | 3,668 | 691 | 15.8523% |
| 2 | 4,360 | 2,950 | 3,668 | 692 | 15.8716% |

Tái lập cùng mapping khi đổi thứ tự input nhưng giữ seed. File đã có được kiểm tra equality trước; notebook không âm thầm ghi đè artifact khác.
Xuất `data/interim/02_group_folds_train.csv`, schema chính xác `id,fold_id`, 13,078 ID, chỉ official train.
Chưa có metric model hoặc threshold tuning; official test chỉ được dùng kiểm kê integrity.

## Official feature EDA

`03_matrix_X_features.csv` có 18,995 dòng và 13 cột (`id` + 12 features), là representation của chính core URLs, không phải dataset mới.
Nối metadata theo ID, chỉ dùng 13,078 core train URL (benign 11,004, phishing 2,074) cho quantile, boxplot, Spearman và IQR diagnostics.
Đối chiếu đúng thứ tự 12 cột `keep` trong dictionary; không đưa `is_https`, source/tier/split/label hoặc error metadata vào X.
Các `train_check` chưa đo/đo trên full official train của dictionary không đồng nhất với core train; chỉ báo cáo, không tự sửa file của Hy.
Không fit scaler, chọn feature hoặc xóa/cap outlier. Các feature thưa có IQR=0 nên số điểm ngoài ngưỡng không đồng nghĩa số dữ liệu lỗi.

## Bàn giao cho Phúc

| File local | Nội dung |
| --- | --- |
| `data/interim/02_group_folds_train.csv` | 13,078 train IDs, cột `id,fold_id`, folds 0–2 |
| `data/interim/03_matrix_X_features.csv` | 18,995 core IDs, đủ 12 features theo thứ tự dictionary |
| `data/interim/03_registrable_domains.csv` | 18,997 core IDs, domain và error_reason |
| `data/interim/03_excluded_rows.csv` | 2 URL bị loại khỏi X và lý do |
| `data/interim/core_gold_silver.csv` | Metadata và nhãn/split từ Khiêm |

Các CSV là artifact local bị Git bỏ qua; chưa force-add/push. Phúc nối metadata–X–fold bằng ID, fit preprocessing trong training fold, giữ validation/test đúng vai trò.
Runtime predict cần nhánh xử lý parser không resolve; không gán benign hoặc tự bịa score cho URL lỗi.
Parser/features local hiện khớp `65b1054`; artifacts được tạo từ đúng mã đã merge và đối chiếu với dictionary cùng phiên bản. Không có thay đổi công thức parser/features trong phần việc Hưng.

## Đề xuất để nhóm ghi decisions.md — chưa tự sửa quyết định

1. Xác nhận Gold/Silver làm baseline chính; 2 unresolved train được giữ trong core nhưng ngoài CV/X, báo cáo coverage và IDs.
2. Ghim parser/PSL/IDNA version, private suffix=False và policy missing/IP; không gom unresolved thành một shared group.
3. Chốt fold artifact seed 42, 3 group folds trên eligible official train; validation ít positive chỉ bổ sung, test không dùng chọn features/model/threshold.
4. Giữ schema official 12 cột; xem xét cột hằng/thưa/tương quan trong pipeline của Phúc, không tự feature selection ngoài fold. Chốt định nghĩa PR-AUC riêng trong baseline.

## Kết luận

Phần EDA, domain audit và Group CV của Hưng đã chạy trên dữ liệu thật với phạm vi loại mẫu được công khai. Hai URL unresolved và phạm vi/độ tin cậy của nhãn feed vẫn là giới hạn, không phải lý do tự sửa nhãn hoặc split.
Các kết quả là mô tả dữ liệu và kiểm định integrity, không xác nhận chất lượng model hoặc khả năng khái quát ra ngoài nguồn NCSC/core hiện tại.
