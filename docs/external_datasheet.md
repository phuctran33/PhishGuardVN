# External URL Pilot Datasheet

**Trạng thái:** Đã tạo và kiểm toán hai candidate CSV. Danh sách phục vụ rà soát thủ công; nhãn chưa được review cuối và chưa dùng để tính metric external.

## 1. Mục đích và tiêu chí lấy mẫu

Pilot thu thập URL mới nhằm rà soát khả năng tổng quát hóa ngoài Core. Không dùng candidate để huấn luyện, chọn đặc trưng/mô hình hoặc điều chỉnh threshold. Chỉ mẫu được review và chấp nhận mới có thể chuyển thành external evaluation set.

Mục tiêu tham khảo là 150–300 ứng viên, không phải quota bắt buộc. Snapshot hiện có 106 dòng (74 phishing, 32 benign). Ưu tiên provenance và bằng chứng rà soát được hơn việc lấp đủ số lượng. Danh sách được chọn theo nguồn sẵn có, không phải mẫu ngẫu nhiên đại diện toàn bộ website tại Việt Nam.

## 2. Tệp và kết quả audit

| Tệp | Nhãn ứng viên | Đầu vào | Giữ sau audit độc lập | Overlap Core | Trùng/xung đột | Pending |
|---|---|---:|---:|---:|---:|---:|
| pilot_phishing_candidates.csv | phishing | 74 | 74 | 0 | 0 | 74 |
| pilot_benign_candidates.csv | benign | 32 | 32 | 0 | 0 | 32 |
| **Tổng** |  | **106** | **106** | **0** | **0** | **106** |

Audit chuẩn hóa URL rồi so URL, hostname và registrable domain với dataset_url.csv và URL trong vn_compphish.csv. Không phát hiện URL lỗi parse, thiếu evidence_ref, trùng nội bộ hoặc xung đột khóa giữa hai nhãn.

### Audit log

| Ngày | Phạm vi | Kiểm tra | Kết quả |
|---|---|---|---|
| 2026-11-07 | 74 phishing + 32 benign | URL chuẩn hóa, hostname, registrable domain với Core | 0 overlap |
| 2026-11-07 | Trong từng tệp và giữa hai nhãn | ID/URL/hostname/registrable-domain trùng hoặc xung đột nhãn | 0 |
| 2026-11-07 | Tất cả candidate rows | URL parse và evidence_ref | 0 lỗi parse; 106/106 có evidence_ref |
| 2026-11-07 | Hai CSV hiện có | Số dòng giữ/loại trong lần audit độc lập | Giữ 106; loại 0 |

Notebook 05 tính lại audit log từ CSV khi chạy và hiển thị các dòng bị loại nếu có. Notebook 06 chỉ ghi candidate vượt qua bộ lọc, không lưu danh sách bị loại trước khi ghi CSV; tổng số URL bị loại trong toàn bộ quá trình crawl không thể khôi phục từ snapshot này.

## 3. Nguồn, phương thức thu thập và bằng chứng nhãn

### Phishing

| Nguồn | Số dòng | label_source | Bằng chứng lưu |
|---|---:|---|---|
| Tín Nhiệm Mạng | 74 | source_listing | evidence_ref trỏ tới trang danh sách URL lừa đảo tương ứng |

Ứng viên được lấy từ danh sách Tín Nhiệm Mạng. Đây là nguồn phát hiện/cảnh báo, không chứng minh URL hiện còn hoạt động hoặc còn độc hại. CSV không có mẫu nào được PhishTank xác nhận. Cần review thời điểm quan sát và bằng chứng theo từng URL.

### Benign

| Nguồn | Số dòng | label_source | Bằng chứng lưu |
|---|---:|---|---|
| Website doanh nghiệp chính thức | 18 | official_site_or_authoritative_listing | Website hoặc trang giới thiệu doanh nghiệp |
| Danh bạ hội viên VNBA | 6 | official_site_or_authoritative_listing | Hồ sơ hội viên liên kết website |
| Cổng thông tin Chính phủ | 4 | official_site_or_authoritative_listing | Danh sách cơ quan/địa phương |
| Danh bạ tin nhiệm Tín Nhiệm Mạng | 3 | official_site_or_authoritative_listing | Trang danh bạ ghi URL |
| Hồ sơ doanh nghiệp AEON | 1 | official_site_or_authoritative_listing | Hồ sơ AEON Việt Nam nêu AEONESHOP |

Các URL tham chiếu được lưu trong evidence_ref, gồm [Cổng thông tin Chính phủ](https://vietnam.gov.vn/default.aspx?countryId=501&typeId=1), [danh bạ hội viên VNBA](https://vnba.org.vn/vi/vnba/member) và trang/hồ sơ của từng tổ chức. Bằng chứng giúp truy nguyên website nhưng không thay việc kiểm tra chủ sở hữu, trang đích, chuyển hướng và nội dung hiện tại.

Cả 106 dòng có evidence_ref và label_source. label là nhãn ứng viên; toàn bộ review_status vẫn pending.

## 4. Thời gian thu thập

| Trường | Phishing | Benign | Diễn giải |
|---|---:|---:|---|
| scraped_at | 74/74: 2026-11-07 04:50:10.940448 UTC | 32/32: 2026-11-07 04:50:10.940448 UTC | Thời điểm ghi nhận trong lượt thu thập |
| collected_at | 74/74 để trống | 32/32 để trống | Nguồn không cung cấp ngày URL được phát hiện/sự kiện |

Hai lớp không có độ phủ thời gian sự kiện; timestamp giống nhau không tạo thành mẫu theo thời gian. Snapshot này chưa hỗ trợ temporal holdout.

## 5. Schema CSV

| Trường | Ý nghĩa |
|---|---|
| id | Mã bản ghi duy nhất |
| url, url_norm | URL ứng viên và URL chuẩn hóa |
| hostname, registrable_domain | Host và domain gốc theo PSL |
| label | Nhãn ứng viên: phishing hoặc benign |
| source | Nguồn phát hiện/nhận diện URL |
| label_source | Loại căn cứ đề xuất nhãn |
| evidence_ref | URL tham chiếu danh sách/hồ sơ/trang bằng chứng |
| collected_at | Thời gian sự kiện theo nguồn; hiện thiếu ở cả hai lớp |
| scraped_at | Thời điểm ghi nhận, ISO-8601 UTC |
| review_status | Trạng thái review; cả 106 dòng hiện pending |
| review_note | Ghi chú rà soát và giới hạn bằng chứng |
| license_note | Ghi chú quyền lưu/chia sẻ |
| core_overlap | Cờ overlap; trống khi không phát hiện overlap |

## 6. Quyền sử dụng, rủi ro và giới hạn

Các license_note yêu cầu kiểm tra điều khoản nguồn và attribution; đây không phải xác nhận đã có quyền tái phân phối. Trước khi phát hành CSV cần rà điều khoản của từng nguồn. Nếu không được phép chia sẻ URL thô, chỉ chia sẻ metadata được phép và ghi nơi quản lý dữ liệu.

- Phishing hiện chỉ đến từ một nguồn; nhãn dựa trên listing, chưa xác minh độc lập theo thời điểm.
- Benign được nhận diện qua danh bạ/cổng chính thức và trang doanh nghiệp; cần xác minh tổ chức sở hữu và đích đến hiện tại.
- Tất cả mẫu còn pending; chưa có nhãn accepted để tính metric.
- 106 ứng viên thấp hơn mức tham khảo 150–300, nhưng không ép quota khi provenance/bằng chứng chưa đủ.
- Không có collected_at, nên chưa phân tích temporal drift hay tạo temporal holdout.
- Số bị loại trong lần crawl ban đầu không được lưu; số 0 bị loại chỉ áp dụng cho audit độc lập trên hai CSV hiện tại.
- Domain-level dedup không loại trừ mọi campaign hoặc shared-infrastructure leakage.

## 7. Điều kiện chuyển sang external evaluation

Rà từng URL về trang đích/chuyển hướng, đơn vị sở hữu, bằng chứng nhãn và ngày quan sát; ghi quyết định cùng lý do trong review_status/review_note. Chỉ mẫu accepted có căn cứ và quyền sử dụng phù hợp mới đưa vào external evaluation. Không dùng pilot để train, chọn mô hình hay threshold. Không suy luận benign chỉ vì URL không có trong feed phishing.