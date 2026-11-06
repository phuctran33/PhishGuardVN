# Week 5 — Source Audit và Data Reliability

Phạm vi audit: Core gold/silver trong train/validation (CSV ghi train/val). Official Test được giữ cho đánh giá cuối; không hiển thị phân bố nhãn/nguồn Test hoặc dùng Test để chọn mô hình.

Trong kế hoạch thí nghiệm, E1 dùng URL features truyền thống để đo baseline; E2 dùng URL features + Brand Features để đo mức cải thiện khi thêm Brand Features. Đây là định nghĩa thí nghiệm, không phải tên split hay quy tắc lọc Core.

## 1. Source-label audit và phạm vi

Các cột bắt buộc id, url, url_norm, domain, source, label, split có mặt. Audit source × label × split trong notebook dùng 14.665 dòng Core eligible. Cả 5 nguồn trong tập này chỉ có một nhãn: benign gồm tranco (5.105), tinnhiem_web (3.633), tranco_vn (2.159), tinnhiem_org (1.668); phishing gồm tinnhiemmang (2.100). Đây là source-label confounding hoàn toàn theo nguồn, cần nêu rõ khi diễn giải E1/E2.

## 2. Data reliability và case cần rà soát

Parser PSL tự chứa chạy trên 14.665 dòng Core gold/silver train/validation. Kết quả: 0 hostname overlap, 0 registrable-domain overlap giữa train/validation, không có mismatch giữa domain và hostname, không duplicate ID/URL/URL chuẩn hóa. Có 2 URL unresolved_domain:

- 27984223-c2e3-5068-a777-02f4becd0d10 — techcombank.com-ut.xvz (train, phishing).
- 74648118-c397-5d04-ab64-9c2973953892 — vpbank.com.vn-uz.infor (train, phishing).

Hai URL được liệt kê trong core_excluded_cases; không gán registrable domain. Parser dùng urllib.parse, ipaddress, tldextract 5.4.0 và PSL offline không tính private suffix. Không phát hiện overlap tên miền không chứng minh loại trừ mọi campaign/shared-infrastructure leakage.

## 3. Ngày thu thập

Trên toàn dataset, collected_at có 21.661 giá trị không rỗng; mixed-format YYYY-MM-DD và DD/MM/YYYY parse được cả 21.661, còn 31.455 ô thiếu thật. Không có giá trị không rỗng lỗi parse với format mixed, dayfirst=True. Thống kê ngày riêng trong notebook chỉ tính Core eligible. scraped_at là thời điểm scrape, không thay thế collected_at.

## 4. Kết luận gate

Các kiểm tra cấu trúc/overlap theo hostname và registrable domain không phát hiện vấn đề trong Core audit, ngoài hai URL unresolved được nêu trên. Chưa đủ cơ sở kết luận dữ liệu hoàn toàn vượt reliability gate do source-label confounding, thiếu metadata thời gian và giới hạn campaign leakage. Official Test không tham gia các thống kê quyết định.

## 5. URL kiểm thử độc lập và K5.3

Trạng thái: BLOCKED — Chưa hoàn thành thu thập dữ liệu.

K5.3 yêu cầu xây dựng một tập URL bên ngoài có nhãn và nguồn kiểm chứng để đánh giá độc lập khả năng tổng quát hóa của mô hình. Tập dữ liệu này được giữ riêng, không sử dụng để huấn luyện hoặc lựa chọn mô hình/threshold.

Hiện trạng: Tại thời điểm báo cáo, data/external/ vẫn trống. Do hạn chế thời gian, nhóm chưa thu thập và xác minh được các URL ứng viên cho cả hai nhãn benign và phishing.

Vì chưa có pilot dataset thực tế nên chưa thể đánh giá số lượng bản ghi, độ bao phủ hai lớp, overlap với Core hoặc thống kê các trường hợp được giữ và loại.

Hướng xử lý tiếp theo: Tiếp tục thu thập URL từ các nguồn phù hợp, lưu nguồn và bằng chứng nhãn, xác minh quyền sử dụng, sau đó kiểm tra overlap với Core trước khi tạo tập external evaluation chính thức. Các bản ghi chưa được xác minh sẽ không được đưa vào đánh giá.
## 6. Việc cần làm tiếp

1. Báo cáo metric theo nguồn bên cạnh metric tổng thể; nêu source-label confounding khi so E1/E2.
2. Giữ hai URL unresolved trong danh sách loại và theo dõi lỗi parser.
3. Chỉ chuyển K5.3 khỏi blocker khi có dữ liệu external đủ bằng chứng/điều khoản; không ép quota.
4. Giữ Official Test cho đánh giá cuối; không dùng phân bố Test để chọn mô hình/threshold.

Giới hạn: audit dựa trên metadata, không truy cập website, không xác minh độc lập nội dung từng URL và không chứng minh loại bỏ mọi campaign leakage.
