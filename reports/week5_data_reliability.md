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

Trên toàn dataset, collected_at có 21.661 giá trị không rỗng; cả 21.661 parse được với mixed format và dayfirst=True. Còn 31.455 giá trị thiếu. scraped_at là thời điểm scrape, không thay thế collected_at. Notebook báo cáo riêng thống kê thời gian trên Core eligible train/validation và bổ sung thống kê collected_at trên toàn dataset để kiểm tra tính đầy đủ dữ liệu.

## 3. External pilot — provenance và audit log

Notebook 05 đọc `benign_candidates.csv` và `phishing_candidates.csv` cùng ba tệp Core. Phần này chỉ đối chiếu metadata, không crawl, không mở URL đích và không ghi đè CSV.

| Tệp | Nhãn ứng viên | Đầu vào | Giữ sau audit | Overlap Core | Trùng/xung đột | Pending |
|---|---|---:|---:|---:|---:|---:|
| `phishing_candidates.csv` | phishing | 138 | 138 | 0 | 0 | 138 |
| `benign_candidates.csv` | benign | 29 | 29 | 0 | 0 | 29 |
| **Tổng** |  | **167** | **167** | **0** | **0** | **167** |

Audit snapshot ngày 2026-11-07 so URL chuẩn hóa, hostname và registrable domain với `dataset_url.csv`, `vn_compphish.csv` và `abuse_type.csv`; đồng thời kiểm tra trùng ID/URL/hostname/domain, xung đột nhãn, URL parse, `evidence_ref` và giá trị `core_overlap` đã lưu. Kết quả: 0 overlap, 0 duplicate/conflict, 0 parse error, 0 evidence_ref thiếu; cả 167 dòng được giữ, 0 dòng bị loại trong lần audit độc lập. `core_overlap` được ghi là `No overlap detected` cho cả hai lớp.



### Provenance và căn cứ nhãn

#### Phishing

| Nguồn | Số dòng | Căn cứ trong `label_source`/`evidence_ref` |
|---|---:|---|
| NCSC warning republished by Dak Lak government | 44 | `historical_public_fraud_warning`; cảnh báo NCSC được đăng lại |
| ACB official list of fake websites | 38 | `historical_public_fraud_warning`; danh sách cảnh báo của ACB |
| NCSC warning republished by Nghe An tech centre | 33 | `historical_public_fraud_warning`; cảnh báo NCSC được đăng lại |
| Quang Ngai police publication of NCSC warning | 10 | `historical_public_fraud_warning`; cảnh báo được công an tỉnh đăng |
| Agribank official warning of spoofed domains | 6 | `historical_public_fraud_warning` |
| BIDV official consumer fraud warning | 4 | `historical_public_fraud_warning` |
| Bac Ninh government local public-service scam alert | 1 | `historical_public_fraud_warning` |
| NCSC weekly scam warnings on Ministry portal | 1 | `historical_public_fraud_warning` |
| VNCERT/CC warning on Ministry portal | 1 | `historical_public_fraud_warning` |
| **Tổng** | **138** | |

Các bản đăng lại cảnh báo NCSC không được xem là nguồn/feed độc lập. Nguồn cảnh báo công khai hỗ trợ truy nguyên nhãn lịch sử, nhưng không xác nhận URL hiện còn hoạt động hoặc đang độc hại.

#### Benign

| Nguồn | Số dòng | Căn cứ trong `label_source`/`evidence_ref` |
|---|---:|---|
| Website doanh nghiệp chính thức | 18 | `official_site_or_authoritative_listing` |
| Danh bạ hội viên VNBA | 6 | `official_site_or_authoritative_listing` |
| Cổng thông tin Chính phủ | 4 | `official_site_or_authoritative_listing` |
| Hồ sơ doanh nghiệp AEON | 1 | `official_site_or_authoritative_listing` |
| **Tổng** | **29** | |

**Tách nguồn:** File benign hiện không còn URL nào có nguồn Tín Nhiệm Mạng; 29 ứng viên còn lại đến từ website doanh nghiệp, cổng chính phủ, danh bạ VNBA và hồ sơ AEON.

Cả 167 dòng có `evidence_ref` và đang `pending`. Trang tham chiếu hỗ trợ truy nguyên nhưng chưa thay việc kiểm tra thủ công chủ sở hữu, trang đích, chuyển hướng và nội dung hiện tại.

### Thời gian, quyền sử dụng và tính đại diện

| Trường | Phishing | Benign |
|---|---:|---:|
| `scraped_at` | 138/138 ghi 2026-11-07 04:50:10.940448 UTC | 29/29 ghi 2026-11-07 04:50:10.940448 UTC |
| `collected_at` | 138/138 trống | 29/29 trống |
| `review_status` | 138 pending | 29 pending |
| `core_overlap` | 138 `No overlap detected` | 29 `No overlap detected` |

Không có ngày phát hiện/sự kiện từ nguồn; `scraped_at` là thời điểm snapshot được ghi nhận, không thay thế `collected_at`. Thời điểm giống nhau không tạo thành mẫu temporal. Hai lớp được chọn từ nguồn sẵn có, không phải mẫu ngẫu nhiên hay đại diện cho toàn bộ web Việt Nam.

Các `license_note` yêu cầu kiểm tra điều khoản nguồn/attribution; chưa xác nhận quyền tái phân phối URL. Cần hoàn tất rà soát trước khi phát hành dữ liệu.

## 4. Kết luận kiểm toán

Core audit không phát hiện overlap train/validation hoặc lỗi cấu trúc ngoài hai unresolved URL đã liệt kê. Hai candidate CSV hiện có cùng schema 15 cột, ID duy nhất, URL, label ứng viên, source, review status, evidence reference và kết quả `core_overlap`; audit đối chiếu với ba tệp Core không phát hiện overlap.

Danh sách có **167 candidate**, nằm trong mức tham khảo 150–300 nhưng vẫn là candidate chờ rà soát. Cả 167 dòng còn `pending`, nên chưa phải bộ external evaluation có nhãn accepted và chưa có metric. Ưu tiên provenance/bằng chứng hơn việc bổ sung URL thiếu căn cứ.

## 5. Việc cần hoàn tất trước khi báo cáo metric

1. Rà từng URL về trang đích/chuyển hướng, chủ sở hữu, nội dung, thời điểm và căn cứ nhãn.
2. Ghi quyết định cùng lý do vào `review_status`/`review_note`.
3. Kiểm tra quyền lưu trữ/chia sẻ theo điều khoản từng nguồn.
4. Chỉ đưa mẫu accepted có bằng chứng và quyền sử dụng phù hợp vào external evaluation; giữ pilot ngoài train/validation/Test.
5. Báo cáo metric theo nguồn và nêu source-label confounding; giữ Official Test cho đánh giá cuối.

**Giới hạn:** Kết quả hiện tại là kiểm toán metadata và reference links. Chưa xác minh nội dung trực tiếp từng URL, chưa chứng minh loại trừ mọi campaign leakage và chưa có metric external.

## 6. K5.3 follow-up — format và benchmark gate

Audit ngày 2026-11-08 giữ nguyên 167 candidates nhưng xác nhận scheme/format và cặp feature `slash_cnt/path_len` có thể phân tách 167/167 nhãn ứng viên. Không được dùng kết quả đó làm metric phát hiện phishing. Host-only mới dùng cùng phép biến đổi không phụ thuộc nhãn; slash/path bằng 0 cho cả hai lớp. Source–label confounding vẫn còn ở 13/13 nhóm nguồn, và 88 phishing là cảnh báo NCSC/republication, không phải 88 quan sát từ feed độc lập với Core.

Ledger/review records, kiểm tra overlap với cả snapshot cũ và gate Teacher/verified labels nằm ở [báo cáo K5.3](k53_external_pilot_audit.md), [data dictionary](../data/external/README.md) và `reports/tables/external_pilot/`. Cohort cũ phục hồi được 74 phishing (75 dòng kể header) + 32 benign, đều pending, được giữ riêng; không tự nhận có manifest 75 URL. Benchmark hiện PREPARED/BLOCKED, không có metric thật. Trạng thái snapshot trước review được giữ trong các bảng nguồn phía trên.

### K5.3 — review tài liệu bổ sung ngày 2026-11-08

`k53_reviews.csv` đã có quyết định theo từng ID: 99 verified trong phạm vi tài liệu lịch sử (92 phishing, 7 benign), 68 pending, 0 rejected. Reviewer là Codex, method `ai_document_review`; không có human verification mới. Tài liệu nguồn có SHA256, thời điểm đọc và locator ở `k53_document_sources.csv`. Không thay CSV gốc hoặc label; không xác nhận site hiện tại/full URL. 13 candidate bỏ `www.` so với nguồn vẫn pending, cùng các reference không đủ căn cứ. Chi tiết/định nghĩa nhãn/giới hạn xem báo cáo K5.3 được tái tạo từ ledger. Cohort lịch sử trong Git xác định đúng 74 bản ghi, 75 dòng gồm header; không tạo thêm một URL. Còn thiếu Teacher finalized để chạy recall; source–label confounding chưa được giải quyết nên không công bố FPR/generalization chính thức.
