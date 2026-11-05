External URL Evaluation Datasheet (v1)
1. Mục đích
Tạo một tập URL độc lập để kiểm tra khả năng tổng quát hóa của mô hình trên dữ liệu ngoài Core. Tập này được giữ riêng, không tự động nhập vào train, validation hoặc test hiện tại.
2. Phạm vi và nhãn
Pilot tập trung vào URL liên quan đến website/dịch vụ tại Việt Nam, ưu tiên có nguồn và bằng chứng có thể kiểm tra. Cần có cả hai nhãn:
- phishing: URL được nguồn chống lừa đảo/abuse xác nhận hoặc được người rà soát xác minh có bằng chứng.
- benign: URL thuộc website chính thức/nguồn đáng tin cậy và đã được xác minh. Việc URL không xuất hiện trong danh sách phishing không đủ để gán nhãn benign.
Dự kiến thu thập khoảng 150–300 URL ứng viên cho pilot ban đầu. Đây là mục tiêu thu thập, không phải số lượng đã hoàn thành. Cần có nhiều nguồn cho mỗi lớp để tránh lặp lại tình trạng một nguồn tương ứng duy nhất với một nhãn như trong audit Core.
3. Thông tin cần lưu cho mỗi URL
Trường	Ý nghĩa
id	Mã định danh duy nhất của bản ghi
url	URL gốc
url_norm	URL sau chuẩn hóa theo quy tắc dự án
domain	Hostname/domain được trích xuất
label	phishing hoặc benign
source	Tên nguồn thu thập
label_source	Căn cứ tạo nhãn: feed, danh sách tin cậy hoặc rà soát thủ công
evidence_ref	Liên kết hoặc ghi chú bằng chứng cho nhãn
collected_at	Thời điểm nguồn ghi nhận URL/sự kiện, nếu có
scraped_at	Thời điểm nhóm thu thập dữ liệu
review_status	pending, accepted, rejected hoặc disputed
license_note	Giấy phép/điều khoản và ghi chú quyền sử dụng


Các trường trên là đề xuất cho pilot; không có nghĩa tất cả đã tồn tại trong dataset_url.csv hiện tại.
4. Quy trình chọn và rà soát
    1. Ghi nhận nguồn, ngày thu thập và điều khoản sử dụng trước khi đưa URL vào pilot.
    2. Chỉ chấp nhận nhãn có căn cứ. Bản ghi chưa rõ hoặc có nhãn mâu thuẫn được giữ ở trạng thái pending/`disputed`, không dùng làm dữ liệu đánh giá.
    3. Chuẩn hóa URL, loại trùng theo url/`url_norm` và rà soát domain/campaign lặp lại.
    4. Kiểm tra overlap với Core và các split hiện tại. Tập external phải được giữ tách biệt; không dùng để huấn luyện hoặc điều chỉnh threshold trước lần đánh giá cuối.
    5. Lưu nhật ký thay đổi nhãn và quyết định rà soát để có thể truy vết.
    5. Quyền sử dụng và chia sẻ
    Chỉ đưa dữ liệu thô vào repository khi giấy phép/điều khoản nguồn và chính sách Git của dự án cho phép. Nếu không được phép phân phối lại, giữ dữ liệu ở vị trí được quản lý phù hợp và chỉ công bố metadata hoặc thông tin nguồn có thể chia sẻ. Không suy diễn rằng dữ liệu công khai đồng nghĩa với quyền tái phân phối.
    6. Lưu ý từ kiểm toán Core
    Audit hiện tại trên dataset_url.csv ghi nhận 53.116 bản ghi và 7 nguồn; mỗi nguồn chỉ chứa một nhãn. Ngoài ra, collected_at thiếu 91,32% và scraped_at thiếu 79,69% bản ghi. Vì vậy, pilot cần ghi rõ nguồn, căn cứ nhãn và thời gian ngay từ đầu; đồng thời nên có nhiều nguồn cho mỗi lớp để giảm phụ thuộc vào source-label correlation.
