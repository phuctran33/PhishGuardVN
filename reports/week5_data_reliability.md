# Week 5 — Source Audit và Data Reliability


Phạm vi gồm audit nguồn/nhãn và reliability của Core gold/silver train/validation, cùng kết quả kiểm tra candidate CSV external. Official Test được giữ cho đánh giá cuối; không dùng phân bố nhãn/nguồn Test để chọn mô hình hay threshold.

Trong thiết kế thí nghiệm, E1 dùng URL features truyền thống làm baseline; E2 dùng URL features cùng Brand Features để đo mức cải thiện. Đây là định nghĩa thí nghiệm, không phải tên split hay quy tắc lọc Core.

## 1. Source-label audit trong Core

Audit dùng 14.665 dòng Core eligible gold/silver trong train/validation. Năm nguồn trong phạm vi này mỗi nguồn chỉ có một nhãn:

| Nhãn | Nguồn | Số dòng |
|---|---|---:|
| benign | tranco | 5.105 |
| benign | tinnhiem_web | 3.633 |
| benign | tranco_vn | 2.159 |
| benign | tinnhiem_org | 1.668 |
| phishing | tinnhiemmang | 2.100 |

Đây là source-label confounding hoàn toàn theo nguồn trong phạm vi audit. Khi diễn giải E1/E2 cần nêu giới hạn này; metric tổng thể không tách được ảnh hưởng của nhãn khỏi nguồn.

## 2. Reliability của Core

Parser PSL offline chạy trên 14.665 dòng Core eligible train/validation. Kết quả:

- 0 hostname overlap và 0 registrable-domain overlap giữa train và validation.
- Không có mismatch giữa hostname parse từ URL và hostname lưu trong cột domain.
- Không có duplicate ID, URL hoặc URL chuẩn hóa.
- Có 2 URL unresolved_domain, không được gán registrable domain và đã nằm trong core_exclusions.csv:
  - 27984223-c2e3-5068-a777-02f4becd0d10 — techcombank.com-ut.xvz (train, phishing).
  - 74648118-c397-5d04-ab64-9c2973953892 — vpbank.com.vn-uz.infor (train, phishing).

Parser dùng urllib.parse, ipaddress, tldextract 5.4.0 và PSL offline, không tính private suffix. Không phát hiện domain overlap không chứng minh đã loại trừ mọi campaign leakage/shared infrastructure.

### Thời gian thu thập trong Core

Trên toàn dataset, collected_at có 21.661 giá trị không rỗng; cả 21.661 parse được với mixed format và dayfirst=True. Còn 31.455 giá trị thiếu. scraped_at là thời điểm scrape, không thay thế collected_at. Notebook chỉ hiển thị thống kê Core eligible và không dùng phân bố Official Test.

## 3. External pilot — provenance và audit log

Notebook 05 đọc hai CSV candidate cùng Core. Phần này chỉ đối chiếu metadata, không crawl, không mở URL đích và không ghi đè CSV.

| Tệp | Nhãn ứng viên | Đầu vào | Giữ sau audit | Overlap Core | Trùng/xung đột | Pending |
|---|---|---:|---:|---:|---:|---:|
| pilot_phishing_candidates.csv | phishing | 74 | 74 | 0 | 0 | 74 |
| pilot_benign_candidates.csv | benign | 32 | 32 | 0 | 0 | 32 |
| **Tổng** |  | **106** | **106** | **0** | **0** | **106** |

Audit ngày 2026-11-07 so URL chuẩn hóa, hostname và registrable domain với toàn bộ dataset_url.csv và URL trong vn_compphish.csv; kiểm tra trùng ID/URL/hostname/domain, xung đột nhãn, URL parse và evidence_ref. Kết quả: 0 overlap, 0 duplicate/conflict, 0 parse error, 0 evidence_ref thiếu; giữ 106, loại 0 dòng trong lần audit độc lập.

Các dòng collector loại trước khi ghi CSV không được lưu; tổng số loại ở bước crawl không thể phục dựng từ snapshot hiện tại. Bảng trên là audit log cho hai CSV đang có, không đại diện mọi URL crawler từng xử lý.

### Provenance và căn cứ nhãn

| Lớp | Nguồn | Số dòng | Căn cứ trong label_source/evidence_ref |
|---|---|---:|---|
| phishing | Tín Nhiệm Mạng | 74 | source_listing; liên kết tới listing URL lừa đảo |
| benign | Website doanh nghiệp chính thức | 18 | official_site_or_authoritative_listing; website/trang giới thiệu |
| benign | Danh bạ hội viên VNBA | 6 | official_site_or_authoritative_listing; hồ sơ hội viên và website |
| benign | Cổng thông tin Chính phủ | 4 | official_site_or_authoritative_listing; danh sách cơ quan/địa phương |
| benign | Danh bạ tin nhiệm Tín Nhiệm Mạng | 3 | official_site_or_authoritative_listing; trang danh bạ |
| benign | Hồ sơ doanh nghiệp AEON | 1 | official_site_or_authoritative_listing; hồ sơ nêu AEONESHOP |

Cả 106 dòng có evidence_ref và đang pending. Tín Nhiệm Mạng là nguồn phát hiện phishing, không xác nhận tình trạng độc hại hiện tại. Nguồn chính thức giúp truy nguyên site benign nhưng chưa thay việc kiểm tra thủ công chủ sở hữu, trang đích, chuyển hướng và nội dung.

### Thời gian, quyền sử dụng và tính đại diện

| Trường | Phishing | Benign |
|---|---:|---:|
| scraped_at | 74/74 ghi 2026-11-07 04:50:10.940448 UTC | 32/32 ghi 2026-11-07 04:50:10.940448 UTC |
| collected_at | 74/74 trống | 32/32 trống |
| review_status | 74 pending | 32 pending |

Không có ngày phát hiện/sự kiện từ nguồn; timestamp giống nhau không tạo thành mẫu temporal. Mẫu có domain gốc riêng biệt nhưng được chọn theo nguồn sẵn có, không phải mẫu ngẫu nhiên hay đại diện cho web Việt Nam.

Các license_note yêu cầu kiểm tra điều khoản nguồn/attribution; chưa xác nhận quyền tái phân phối URL. Cần hoàn tất rà soát trước khi phát hành dữ liệu.

## 4. Kết luận kiểm toán

Core audit không phát hiện overlap train/validation hoặc lỗi cấu trúc ngoài hai unresolved URL đã liệt kê. Candidate CSV hiện đã được tạo với ID, URL, label ứng viên, source, review_status, evidence_ref và kết quả audit; không còn tình trạng chưa có candidate pilot.

Danh sách có 106 candidate, thấp hơn mức tham khảo 150–300 nhưng không vi phạm quota vì đây không phải chỉ tiêu bắt buộc. Cả 106 dòng còn pending nên hiện phù hợp cho bước rà soát thủ công; chưa phải bộ external evaluation có nhãn accepted và chưa có metric. Ưu tiên provenance/bằng chứng hơn việc bổ sung URL thiếu căn cứ.

## 5. Việc cần hoàn tất trước khi báo cáo metric

1. Rà từng URL về trang đích/chuyển hướng, chủ sở hữu, nội dung, thời điểm và căn cứ nhãn.
2. Ghi quyết định cùng lý do vào review_status/review_note.
3. Kiểm tra quyền lưu trữ/chia sẻ theo điều khoản từng nguồn.
4. Chỉ đưa mẫu accepted có bằng chứng và quyền sử dụng phù hợp vào external evaluation; giữ pilot ngoài train/validation/Test.
5. Báo cáo metric theo nguồn và nêu source-label confounding; giữ Official Test cho đánh giá cuối.

**Giới hạn:** Kết quả hiện tại là kiểm toán metadata và reference links. Chưa xác minh nội dung trực tiếp từng URL, chưa chứng minh loại trừ mọi campaign leakage và chưa có metric external.