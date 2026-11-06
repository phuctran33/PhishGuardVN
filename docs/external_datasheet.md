# External URL Evaluation Datasheet (v1)

## 1. Mục đích và trạng thái

Tập external được xây dựng nhằm đánh giá khả năng tổng quát hóa của mô hình trên các URL mới, độc lập với Core train/validation/official Test. Tập này không được sử dụng để huấn luyện hoặc lựa chọn mô hình/threshold.

Trạng thái hiện tại: BLOCKED — Chưa có pilot URL thực tế được thu thập và xác minh.

Tài liệu này chỉ mô tả protocol và schema dự kiến, chưa phải dataset pilot.
Theo đề cương đồ án (trang 2), quy mô dự kiến khoảng 100–300 URL có nhãn và nguồn kiểm chứng nếu thu thập đủ dữ liệu đáng tin cậy; đây là mục tiêu có điều kiện, không phải quota bắt buộc.
## 2. Phạm vi và tiêu chí nhãn

Pilot dự kiến tập trung vào URL liên quan đến website/dịch vụ tại Việt Nam, gồm hai lớp:

phishing: URL có bằng chứng từ nguồn cảnh báo phishing hoặc được người rà soát xác minh.

benign: URL thuộc website chính thức, có thể xác minh nguồn gốc và đơn vị sở hữu.

pending / disputed: URL chưa đủ bằng chứng hoặc có thông tin nhãn mâu thuẫn; không đưa vào tập đánh giá.

Không suy luận nhãn benign chỉ từ việc URL không xuất hiện trên feed phishing.

## 3. Schema pilot CSV

| Trường | Ý nghĩa |
|---|---|
| id | Mã bản ghi duy nhất |
| url, url_norm | URL thu thập và URL chuẩn hóa |
| hostname, registrable_domain | Host chuẩn hóa và nhóm theo PSL |
| label | phishing hoặc benign; để trống khi chưa xác minh |
| source | Tên feed/danh sách/đầu mối thu thập |
| label_source | Feed, danh sách tin cậy hoặc review thủ công |
| evidence_ref | URL/ID tham chiếu hoặc ghi chú bằng chứng |
| collected_at | Thời điểm sự kiện theo nguồn |
| scraped_at | Thời điểm nhóm thu thập (ISO-8601 UTC) |
| review_status | pending, accepted, rejected hoặc disputed |
| review_note | Lý do quyết định và case bị loại |
| license_note | Điều khoản lưu/chia sẻ và hạn chế |
| core_overlap | Cờ overlap URL/hostname/registrable domain với Core |
| exclusion_reason | Lý do loại; trống nếu chưa loại |

Chỉ lưu URL thô trong repository nếu giấy phép/điều khoản cho phép. Nếu không, lưu metadata được phép và ghi rõ vị trí quản lý dữ liệu.

## 4. Quy trình thu thập, rà soát và loại

1. Lấy ứng viên từ nguồn ngoài Core; có thể thu thập theo feed/danh sách, không cần tìm từng URL thủ công.
2. Ghi source, thời điểm thu thập, điều khoản sử dụng và bằng chứng nhãn.
3. Chuẩn hóa URL, loại trùng URL/URL chuẩn hóa và rà soát domain/campaign lặp.
4. Đối chiếu membership với toàn bộ Core để cách ly URL/hostname/registrable-domain overlap; phép so sánh không dùng nhãn hay metric Official Test.
5. Chỉ chấp nhận case có đủ bằng chứng, review status rõ và quyền sử dụng phù hợp; ghi từng case cùng lý do giữ/loại.
6. Giữ pilot tách khỏi train/validation/Test; không dùng để huấn luyện hoặc chọn threshold trước đánh giá cuối.

## 5. Blocker và dữ liệu cần có

Hiện trạng: Thư mục data/external/ đang trống, chưa có pilot CSV hoặc danh sách URL ứng viên để kiểm tra. Do đó, chưa thể đánh giá coverage, phân bố nhãn hoặc overlap với Core.

Blocker: Chưa thu thập được URL mới có đủ hai nhãn phishing và benign, nguồn rõ ràng và bằng chứng nhãn có thể xác minh.

Để tiếp tục, cần thu thập URL từ các nguồn phù hợp, ghi nhận nguồn, bằng chứng nhãn, thời điểm thu thập và quyền sử dụng. Sau đó, kiểm tra overlap theo URL, hostname và registrable domain với Core trước khi đưa các bản ghi đã được review vào tập external evaluation.

Các URL chưa đủ bằng chứng hoặc có nhãn mâu thuẫn sẽ không được sử dụng.
## 6. Parser và PSL policy

Notebook audit dùng parser tự chứa với urllib.parse, ipaddress và tldextract 5.4.0; PSL chạy offline, không tính private suffix. Hostname được chuẩn hóa chữ thường, bỏ dấu chấm cuối, IDN chuyển sang Punycode. IP hợp lệ không có registrable domain để làm group. Lỗi parser được giữ cùng ID/URL để rà soát.
