# External URL Pilot Datasheet

**Trạng thái:** PILOT. Hai CSV gốc giữ nguyên; ledger tách biệt ghi review tài liệu lịch sử do AI thực hiện, chưa có metric external hoặc human verification mới.

**Cập nhật K5.3 (2026-11-08): PILOT / PREPARED–BLOCKED.** Audit bổ sung phát hiện format/scheme và `slash_cnt/path_len` phân tách đúng 167/167 **nhãn ứng viên** trên cùng snapshot; đây là collection artifact, không phải khả năng phát hiện phishing. Biểu diễn host-only đã thống nhất cho cả hai lớp bằng parser/feature extractor chính thức, nhưng 13/13 nhóm nguồn vẫn chỉ có một nhãn. Không tuyên bố đã loại source/campaign leakage.

Xem [báo cáo K5.3](../reports/k53_external_pilot_audit.md), [data dictionary và lệnh tái lập](../data/external/README.md), `reports/tables/external_pilot/` và `data/external/derived/`. Hai CSV 15 cột bên dưới vẫn là nguồn nguyên trạng, không bị ghi đè hoặc đổi nhãn. Ledger canonical mới có đủ raw_url/normalized_url/model input/source reference/review evidence; raw CSV vẫn pending; ledger overlay có 99 verified theo tài liệu lịch sử (92 phishing / 7 benign), 68 pending, 0 rejected. Sau xác nhận kiểm tra lại của Hưng, trình bày hiện tại là **99 human-checked**, ghi riêng trong `reports/annotations/k53_human_check_confirmation.csv` theo ID/signature. Đây là xác nhận do reviewer tự báo cáo, không mở rộng sang 68 pending hoặc xác minh website hiện tại/full URL. Các trường method/reviewer trong ledger PR #13 giữ lịch sử lần đối chiếu tài liệu ban đầu, không bị đổi tên để giả thành một quy trình khác. Chưa có Teacher bundle đã chốt để chấm metric.

Lịch sử Git phục hồi riêng **74 phishing + 32 benign** tại `data/external/history/2026-11-07/`. File phishing có 75 dòng gồm header; không tìm thấy manifest chứng minh một cohort đúng 75 URL. 74 phishing cũ đến từ tinnhiemmang và 29 benign trùng snapshot mới; không gộp thành benchmark độc lập hoặc nhận tất cả đã verified.

## 1. Mục đích và tiêu chí lấy mẫu

Pilot thu thập URL mới nhằm rà soát khả năng tổng quát hóa ngoài Core. Không dùng candidate để huấn luyện, chọn đặc trưng/mô hình hoặc điều chỉnh threshold. Chỉ mẫu được review và chấp nhận mới có thể chuyển thành external evaluation set.


## 2. Tệp và kết quả audit

| Tệp | Nhãn ứng viên | Đầu vào | Giữ sau audit độc lập | Overlap Core | Trùng/xung đột | Pending |
|---|---|---:|---:|---:|---:|---:|
| `phishing_candidates.csv` | phishing | 138 | 138 | 0 | 0 | 138 |
| `benign_candidates.csv` | benign | 29 | 29 | 0 | 0 | 29 |
| **Tổng** |  | **167** | **167** | **0** | **0** | **167** |

Audit chuẩn hóa URL rồi so URL, hostname và registrable domain với `dataset_url.csv`, `vn_compphish.csv` và `abuse_type.csv`. Không phát hiện URL lỗi parse, thiếu `evidence_ref`, overlap Core, trùng nội bộ hoặc xung đột khóa giữa hai nhãn.

### Audit log

| Ngày | Phạm vi | Kiểm tra | Kết quả |
|---|---|---|---|
| 2026-11-07 | 138 phishing + 29 benign | URL chuẩn hóa, hostname, registrable domain với ba tệp Core | 0 overlap |
| 2026-11-07 | Trong từng tệp và giữa hai nhãn | ID/URL/hostname/registrable-domain trùng hoặc xung đột nhãn | 0 |
| 2026-11-07 | Tất cả candidate rows | URL parse và `evidence_ref` | 0 lỗi parse; 167/167 có `evidence_ref` |
| 2026-11-07 | Hai CSV hiện tại | Số dòng giữ/loại trong lần audit độc lập | Giữ 167; loại 0 |

Notebook 05 tính lại audit log từ hai CSV hiện tại khi chạy. Kết quả “giữ 167, loại 0” chỉ áp dụng cho lần audit độc lập trên snapshot này; không đại diện cho số URL có thể đã bị loại ở các bước tuyển chọn trước đó.

## 3. Nguồn, phương thức thu thập và bằng chứng nhãn

### Phishing

| Nguồn ghi trong CSV | Số dòng | Căn cứ nhãn |
|---|---:|---|
| NCSC warning republished by Dak Lak government | 44 | `historical_public_fraud_warning` |
| ACB official list of fake websites | 38 | `historical_public_fraud_warning` |
| NCSC warning republished by Nghe An tech centre | 33 | `historical_public_fraud_warning` |
| Quang Ngai police publication of NCSC warning | 10 | `historical_public_fraud_warning` |
| Agribank official warning of spoofed domains | 6 | `historical_public_fraud_warning` |
| BIDV official consumer fraud warning | 4 | `historical_public_fraud_warning` |
| Bac Ninh government local public-service scam alert | 1 | `historical_public_fraud_warning` |
| NCSC weekly scam warnings on Ministry portal | 1 | `historical_public_fraud_warning` |
| VNCERT/CC warning on Ministry portal | 1 | `historical_public_fraud_warning` |
| **Tổng** | **138** | |

Các cảnh báo được công bố bởi cơ quan, ngân hàng hoặc được đăng lại từ cảnh báo NCSC. Những bản đăng lại không được xem là các feed độc lập. Đây là bằng chứng về cảnh báo/lừa đảo được ghi nhận trong quá khứ, không xác nhận URL hiện còn hoạt động hoặc đang độc hại. Mỗi dòng có `evidence_ref` trỏ tới tài liệu nguồn; review theo ID và scope trong ledger mới; không mặc định đồng nghĩa human verification.

### Benign

| Nguồn ghi trong CSV | Số dòng | Căn cứ nhãn |
|---|---:|---|
| Website doanh nghiệp chính thức (`official_business_site`) | 18 | `official_site_or_authoritative_listing` |
| Danh bạ hội viên VNBA (`vnba_member_directory`) | 6 | `official_site_or_authoritative_listing` |
| Cổng thông tin Chính phủ (`government_portal`) | 4 | `official_site_or_authoritative_listing` |
| Hồ sơ doanh nghiệp AEON (`aeon_official_corporate_profile`) | 1 | `official_site_or_authoritative_listing` |
| **Tổng** | **29** | |

**Tách nguồn:** File benign hiện không còn URL nào có nguồn Tín Nhiệm Mạng; 29 ứng viên còn lại đến từ website doanh nghiệp, cổng chính phủ, danh bạ VNBA và hồ sơ AEON.

Các URL tham chiếu được lưu trong `evidence_ref`, gồm [Cổng thông tin Chính phủ](https://vietnam.gov.vn/default.aspx?countryId=501&typeId=1), [danh bạ hội viên VNBA](https://vnba.org.vn/vi/vnba/member) và trang/hồ sơ của từng tổ chức. Bằng chứng giúp truy nguyên website nhưng không thay việc kiểm tra chủ sở hữu, trang đích, chuyển hướng và nội dung hiện tại.

Trong hai CSV nguồn nguyên trạng, cả 167 dòng có `evidence_ref` và `label_source`; `label` là nhãn ứng viên và `review_status` vẫn `pending`. Trạng thái sau đối chiếu tài liệu được overlay riêng trong ledger K5.3, không ghi đè nguồn.

## 4. Thời gian thu thập

| Trường | Phishing | Benign | Diễn giải |
|---|---:|---:|---|
| `scraped_at` | 138/138: 2026-11-07 04:50:10.940448 UTC | 29/29: 2026-11-07 04:50:10.940448 UTC | Thời điểm snapshot được ghi nhận trong CSV |
| `collected_at` | 138/138 để trống | 29/29 để trống | Nguồn không cung cấp ngày URL được phát hiện/sự kiện |



## 5. Schema CSV

| Trường | Ý nghĩa |
|---|---|
| `id` | Mã bản ghi duy nhất; dùng dạng `ext_pilot_phishing_NNNN` hoặc `ext_pilot_benign_NNNN` |
| `url`, `url_norm` | URL ứng viên nguyên dạng và URL chuẩn hóa; phishing có thể chỉ có hostname nếu nguồn không cung cấp scheme/path |
| `hostname`, `registrable_domain` | Host và domain gốc theo PSL |
| `label` | Nhãn ứng viên: phishing hoặc benign |
| `source` | Nguồn phát hiện/nhận diện URL |
| `label_source` | Loại căn cứ đề xuất nhãn |
| `evidence_ref` | URL tham chiếu danh sách/hồ sơ/trang bằng chứng |
| `collected_at` | Thời gian sự kiện theo nguồn; hiện thiếu ở cả hai lớp |
| `scraped_at` | Thời điểm snapshot được ghi nhận, ISO-8601 UTC |
| `review_status` | Trạng thái review; cả 167 dòng hiện `pending` |
| `review_note` | Ghi chú rà soát và giới hạn bằng chứng |
| `license_note` | Ghi chú quyền lưu/chia sẻ |
| `core_overlap` | Kết quả đối chiếu với ba tệp Core; hiện là `No overlap detected` |

Hai CSV có cùng 15 cột theo cùng thứ tự. `core_overlap` dùng giá trị dễ đọc; notebook 05 lưu chi tiết audit theo URL, hostname và registrable domain.

## 6. Quyền sử dụng, rủi ro và giới hạn

Các `license_note` yêu cầu kiểm tra điều khoản nguồn và attribution; đây không phải xác nhận đã có quyền tái phân phối. Trước khi phát hành CSV cần rà điều khoản của từng nguồn. Nếu không được phép chia sẻ URL thô, chỉ chia sẻ metadata được phép và ghi nơi quản lý dữ liệu.

- Phishing hiện dựa trên cảnh báo công khai trong quá khứ; một số nguồn là bản đăng lại cảnh báo NCSC, không phải feed độc lập. Nhãn chưa xác minh tình trạng hiện tại.
- Benign được nhận diện qua danh bạ/cổng chính thức và trang doanh nghiệp; cần xác minh tổ chức sở hữu và đích đến hiện tại.
- Hai CSV gốc còn `pending`; ledger có subset nhãn lịch sử và xác nhận human-checked riêng của Hưng. Đây không phải xác minh trang đích hiện tại; xem phương pháp và giới hạn trong báo cáo K5.3.
- Snapshot 167 ứng viên nằm trong mức tham khảo 150–300, nhưng số lượng không thay thế yêu cầu review nhãn và quyền sử dụng.
- Không có `collected_at`, nên chưa phân tích temporal drift hay tạo temporal holdout.
- Số bị loại ở bước tuyển chọn trước audit không được ghi nhận; số 0 bị loại chỉ áp dụng cho audit độc lập trên hai CSV hiện tại.
- Domain-level dedup không loại trừ mọi campaign hoặc shared-infrastructure leakage.
- Bản audit K5.3 chỉ gắn cờ domain/hostname chung để review; không tự xóa candidate chỉ vì cùng registrable domain. Core overlap làm dừng eligibility cho evaluation, không xóa dữ liệu nguồn hay đổi nhãn.
- Cảnh báo NCSC được đăng lại có thể vẫn liên quan cơ chế nguồn của Core, dù hostname/domain không giao. 88/138 phishing hiện thuộc nhóm cảnh báo NCSC/republication; nguồn xuất bản mới không chứng minh feed hoặc campaign độc lập.

## 7. Điều kiện chuyển sang external evaluation

Rà từng URL về trang đích/chuyển hướng, đơn vị sở hữu, bằng chứng nhãn và ngày quan sát; ghi quyết định cùng lý do trong `review_status`/`review_note`. Chỉ mẫu accepted có căn cứ và quyền sử dụng phù hợp mới đưa vào external evaluation. Không dùng pilot để train, chọn mô hình hay threshold. Không suy luận benign chỉ vì URL không có trong feed phishing.
