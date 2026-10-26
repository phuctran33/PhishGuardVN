# Phân tích FP/FN và chênh lệch CV–Validation — tuần 4

Phân tích cấu hình `logistic_regression_balanced`, ngưỡng cố định **0,5**. Nhãn phishing = 1 theo PhishVN; “FP/FN” nghĩa là sai so với nhãn trong dataset, không phải xác minh trạng thái website hiện tại. Chỉ đọc chuỗi URL và dữ liệu có sẵn, không truy cập các website. Không thay đổi nhãn, feature, fold, cấu hình hay ngưỡng sau khi xem lỗi.

## 1. Cách chọn và giới hạn mẫu

[04_error_examples.csv](tables/04_error_examples.csv) có **5 FP + 5 FN**, lấy từ dự đoán OOF của cấu hình được chọn. Mỗi loại luân phiên fold 0 → 1 → 2 rồi lặp lại, lấy ID tăng dần trong mỗi fold: **2 mẫu fold 0, 2 mẫu fold 1, 1 mẫu fold 2**. Các dòng không phụ thuộc thứ tự đầu vào. Đây là sửa lỗi lấy `head(5)` trước đây làm tất cả mẫu rơi vào fold 0.

Mẫu nhỏ, xác định theo ID, không lấy ngẫu nhiên hay phân tầng theo nguồn/độ tin cậy/score. Vì vậy chỉ dùng minh họa và tìm giả thuyết; không suy ra tỷ lệ mỗi nguyên nhân trong toàn bộ 3.185 FP hoặc 400 FN. Số lỗi toàn bộ vẫn lấy từ OOF, không lấy từ bảng mẫu. Mỗi dòng CSV đã có observation, hypothesis, next_check; giả thuyết và việc cần kiểm tra được tách khỏi quan sát đã đo.

## 2. Quan sát thực tế

URL dưới đây bỏ scheme và thay dấu chấm bằng `[.]`. Score là đầu ra mô hình của **đúng fold giữ lại**, chưa hiệu chuẩn. Nhãn/nguồn/tier là thông tin đối chiếu, không đưa vào X.

| Loại | Fold | URL | Nhãn gốc / nguồn / tier | Score | Quan sát chính |
|---|---:|---|---|---:|---|
| FP | 0 | `maheir-3v78[.]shop` | benign / tranco / silver | 0,9790 | Có 3 chữ số, 1 gạch nối; kiểm tra LR fold 0 cho thấy hai hạng này tăng logit. |
| FP | 1 | `hoasenholdings[.]vn` | benign / tranco_vn / silver | 0,5332 | Chỉ chữ và dấu chấm, không path/subdomain, vẫn vượt ngưỡng. |
| FP | 2 | `d[.]vjst[.]vn` | benign / tinnhiem_web / gold | 0,9212 | Domain đăng ký `vjst.vn`, 1 subdomain; hạng subdom_cnt tăng logit mạnh trong mô hình fold 2. |
| FP | 0 | `vistarmedia[.]com` | benign / tranco / silver | 0,5631 | Cùng vector 12 feature với 22 benign + 2 phishing trong eligible train. |
| FP | 1 | `zhujuba[.]com` | benign / tranco / silver | 0,5191 | Sát ngưỡng; cùng vector với 75 benign + 19 phishing. |
| FN | 0 | `hhecy[.]space` | phishing / tinnhiemmang / gold | 0,4478 | 11 ký tự, không số/gạch nối/path; cùng vector với 49 benign + 10 phishing. |
| FN | 1 | `freefiremembership[.]com` | phishing / tinnhiemmang / silver | 0,4933 | Có token tên gọi nhưng 12 feature không mã hóa ngữ nghĩa token. |
| FN | 2 | `pinuian[.]top` | phishing / tinnhiemmang / gold | 0,4803 | Cùng đủ 12 feature với hhecy.space dù tên và TLD khác nhau. |
| FN | 0 | `pocinex[.]com` | phishing / tinnhiemmang / gold | 0,4913 | Sát dưới ngưỡng; cùng vector với 99 benign + 19 phishing. |
| FN | 1 | `thongtincongty[.]com` | phishing / tinnhiemmang / gold | 0,4758 | Tên dễ đọc, không số/path/subdomain; feature đếm không hiểu nội dung. |

Các nhóm cùng vector được đếm trên **13.078 dòng eligible train, gồm cả ba fold**, có tính chính mẫu đang xét. Đây là phân tích biểu diễn sau đánh giá, không phải thống kê dùng để fit mô hình hoặc thay nhãn. Không dùng validation/test cho phép đếm này. Trùng vector giữa các URL khác domain không phải bằng chứng trùng domain qua fold; đó là mất thông tin do nén URL thành 12 con số.

Hai URL có cùng vector nhận cùng score nếu đưa vào cùng một mô hình. hhecy.space và pinuian.top có score khác nhau vì chúng được đánh giá bằng mô hình của hai fold khác nhau. Feature hiện tại không mã hóa danh tính TLD hay từ ngữ; không thể phân biệt từng URL trong một nhóm vector trùng nhau. Muốn kiểm chứng cải thiện phải chạy thí nghiệm biểu diễn khác trong train/CV.

Các hạng `z * coefficient` chỉ giải thích phép tính logit so với trung bình train của fold. Chúng đi cùng intercept và các biến tương quan (ví dụ dot_cnt/subdom_cnt), không chứng minh quan hệ nhân quả hoặc tầm quan trọng tổng quát. Script chẩn đoán tái fit đúng từng fold và kiểm tra score khớp OOF ở sai số tuyệt đối ≤ 1e-10.

## 3. Vì sao balanced LR giảm F1 trên validation?

### Kết quả đo

| Đại lượng | CV: gộp OOF | Official validation |
|---|---:|---:|
| Số dòng | 13.078 | 1.585 |
| Phishing / benign | 2.074 / 11.004 | 24 / 1.561 |
| Tỷ lệ phishing | 15,86% | 1,51% |
| TP / FP / FN / TN | 1.674 / 3.185 / 400 / 7.819 | 23 / 646 / 1 / 915 |
| Precision | 34,45% | 3,44% |
| Recall | 80,71% | 95,83% |
| F1 | 48,29% | 6,64% |
| FPR = FP / số benign | 28,94% | 41,38% |

Báo cáo chính chọn mô hình bằng **trung bình F1 từng fold = 0,483148**; bảng trên dùng **F1 từ OOF gộp ≈ 0,4829** để giải thích bằng các số đếm. Hai cách tổng hợp có thể khác nhau. CV là ba mô hình học trên khoảng 2/3 train mỗi lần; validation dùng mô hình fit toàn bộ train. Đây không phải cùng một mô hình được chấm trên hai tập.

**Tỷ lệ lớp thay đổi:** với prevalence π, recall r và FPR f, precision = πr / [πr + (1−π)f]. Giữ recall/FPR OOF và chỉ thay π bằng tỷ lệ validation cho precision khoảng **4,11%**, F1 khoảng **7,82%**. Đây là phép minh họa theo tỷ lệ lớp, không phải điểm đánh giá mới hay phép tách nguyên nhân chính xác. Nó cho thấy precision thấp hơn nhiều có thể xảy ra ngay cả nếu recall/FPR giữ nguyên.

**FPR còn tăng thật:** 41,38% so với 28,94%, nên không thể giải thích toàn bộ chỉ bằng ít phishing. Đối chiếu nguồn của benign:

| Nguồn benign | CV benign / FP / FPR | Validation benign / FP / FPR |
|---|---|---|
| tinnhiem_org | 1.659 / 107 / 6,45% | 9 / 1 / 11,11% |
| tinnhiem_web | 3.362 / 291 / 8,66% | 271 / 62 / 22,88% |
| tranco | 4.170 / 2.299 / 55,13% | 935 / 475 / 50,80% |
| tranco_vn | 1.813 / 488 / 26,92% | 346 / 108 / 31,21% |

Tranco + tranco_vn tăng từ **54,37% lên 82,06% số benign**; đây là hai nguồn có FPR cao trong OOF. FPR trong từng nguồn cũng thay đổi, không đồng loạt tăng. Mean url_len của benign giảm 17,59 → 13,76 và mean subdom_cnt giảm 0,4563 → 0,0660. Đây là bằng chứng khác phân bố nguồn/feature giữa các split; chưa chứng minh cơ chế gây lỗi cụ thể hoặc một thay đổi theo thời gian. Một nguồn có chỉ 9 mẫu validation thì phần trăm rất thiếu ổn định.

**Tác động balanced và độ bất định:** class_weight tăng trọng số mỗi phishing khoảng 11.004 / 2.074 = **5,31 lần** mỗi benign trong lần fit toàn train. Mô hình tìm được nhiều phishing nhưng báo nhầm nhiều ở ngưỡng 0,5; balanced không tự hiệu chuẩn score theo prevalence triển khai. Validation chỉ có 24 phishing: đổi đúng/sai một mẫu làm recall thay đổi **4,17 điểm phần trăm**. Recall 95,83% vì vậy chưa đủ chứng minh mô hình tổng quát hóa tốt. AP cũng giảm từ mean-fold 0,5577 xuống 0,2744; AP chịu ảnh hưởng tỷ lệ lớp và phân bố nên không đọc riêng F1.

Nguồn và nhãn còn bị lẫn: toàn bộ positive của các tập đang xét đến từ tinnhiemmang, các nguồn trên là negative. Không đưa `source` vào X vẫn chưa loại bỏ các dấu hiệu gián tiếp từ nguồn. Không thể kết luận chỉ có prevalence shift hoặc đảm bảo không có source bias vì không trùng domain.

**Quyết định hiện tại:** giữ balanced là cấu hình thắng theo tiêu chí CV F1 đã định trước; ghi rõ đây là baseline thử nghiệm có nhiều cảnh báo nhầm, chưa dùng triển khai. Không đổi winner/threshold vì validation thấp. Bước tiếp theo là kiểm tra thêm nguồn và kiểu URL, thử biểu diễn/mô hình hoặc threshold trong thí nghiệm train/CV riêng; giữ official test chưa chấm.

## 4. Metadata provenance

Snapshot cũ ghi `git_revision = d5555da087399780678d1f97c100c3dc3201eec0`: đó là **HEAD tại thời điểm chạy**, khi code baseline còn sửa/chưa commit trên nhánh kế thừa Hưng. `git_worktree_status` đã ghi trạng thái chưa commit, và toàn bộ **12 hash source/config trong snapshot cũ khớp các file tương ứng ở commit baseline `eb97564`** khi chuẩn hóa CRLF → LF. Vì vậy không diễn giải SHA cũ như commit chứa implementation baseline.

Đã chạy lại baseline sau chỉnh sửa, không thay SHA thủ công. [04_run_metadata.json](tables/04_run_metadata.json) hiện ghi:

- `git_revision`: HEAD nền lúc chạy; không hứa bằng commit tương lai chứa chính file kết quả.
- `captured_at_utc`: thời điểm thu provenance trước khi `save_results` ghi output.
- `git_source_worktree_status` và `source_state`: runtime source có khác HEAD hay không, tách khỏi thay đổi output/notebook/tài liệu.
- `source_sha256_lf` và `source_manifest_sha256`: định danh source/config thực tế, kể cả phần chưa commit.
- `input_sha256`, `artifact_sha256`, versions: định danh handoff, model artifact local và thư viện.

Không thay SHA theo commit mới mà chưa chạy lại: làm vậy sẽ làm sai lịch sử thực nghiệm. Một lần chạy có source đang sửa được ghi rõ `modified_from_head`; người tái lập đối chiếu hash với source trong PR. Artifact model và predictions nằm ở thư mục Git bỏ qua, có thể tạo lại bằng CLI/notebook.

## 5. Tái lập bằng chứng

Chạy bằng Python của `.venv` sau khi đã tạo handoff 01 → 03 → 02:

```bash
python scripts/train_baseline.py
python scripts/analyze_baseline_errors.py
```

Lệnh đầu tạo metrics/predictions/metadata và giữ ghi chú thủ công. Lệnh sau kiểm tra hash handoff/source, tái dựng score đúng fold cho 10 ví dụ và ghi [04_error_diagnostics.json](tables/04_error_diagnostics.json): confusion theo nguồn, feature means, va chạm vector, phép minh họa prevalence và hash prediction/script. Nó chỉ đọc dự đoán train/validation đã lưu; không fit hay dự đoán official test. Bảng nhận xét trong CSV và báo cáo này là phân tích con người cần đối chiếu lại nếu thay dataset/config, không tự suy diễn thành nhận xét mới sau mỗi lần chạy.
