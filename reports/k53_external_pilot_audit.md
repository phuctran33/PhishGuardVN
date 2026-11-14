# K5.3 — External pilot audit và benchmark readiness

**Cập nhật sau merge PR #13:** Hưng xác nhận đã check lại 99 trường hợp đã có bằng chứng tài liệu. Trạng thái trình bày hiện tại: **99 human-checked / 68 pending**, theo [bản xác nhận theo ID/signature](annotations/k53_human_check_confirmation.csv). Đây là xác nhận tự báo cáo theo nhóm; không xác nhận live site/full URL, không nâng 68 pending. Các bảng số học và ledger bên dưới giữ snapshot PR #13. Không có Teacher finalized hoặc external metric.

## A. Audit trước và sau

| Kiểm tra | Trước (CSV nguồn) | Sau audit / chuẩn hóa |
|---|---:|---:|
| Candidates | 167 | 167, giữ toàn bộ ID/raw_url/label |
| Phishing / benign | 138 / 29 | Không đổi nhãn |
| Verified / pending / rejected | 0 / 167 / 0 | 99 / 68 / 0 |
| Duplicate raw URL / host / registrable domain | Kiểm tra lại từ dữ liệu | 0 / 0 / 0 |
| Overlap với toàn PhishVN theo URL / hostname / domain | Kiểm tra 53,116 URL và bảng companion | 0 / 0 / 0 |
| Overlap với cohort cũ theo host | Chưa tách cohort rõ | 29 rows; xem bảng overlap, không coi là hai holdout độc lập |
| URL parse không hợp lệ | Kiểm tra lại | 0; không gán vector số giả |
| Metadata url_norm khác phép chuẩn hóa giữ case | Audit legacy hạ chữ thường toàn URL | 1 cảnh báo; giữ raw URL, không loại candidate |
| Format strata / pure strata | 2 / 2 | 1 / 0 |
| Nhãn ứng viên khớp majority của format strata | 167/167 | 138/167; không phải metric model |
| Nhóm nguồn chỉ một nhãn | 13/13 | Vẫn 13/13 |

Trong raw, phishing không có HTTP scheme, benign có scheme và path. Cặp **slash_cnt/path_len của extractor E1 đã freeze** cũng phân tách 167/167 nhãn ứng viên. Như vậy bỏ is_https khỏi X chưa loại được artifact format. Đây là kiểm tra impurity trên chính candidate labels, không phải accuracy hay năng lực phát hiện phishing đã xác minh.

Sau phép biến đổi host-only không phụ thuộc nhãn, slash_cnt/path_len bằng 0 cho mọi input; chỉ còn một format stratum. Con số 138/167 là majority-class purity, không phải kết quả inference. Điều đã kiểm chứng là các dấu hiệu scheme/path này đã trở thành hằng trong biểu diễn mới; **chưa chứng minh loại hết source/campaign/lexical leakage hoặc đo khả năng tổng quát hóa**.

Audit legacy từng hạ chữ thường cả path/query: `ext_pilot_benign_0031` có raw path `/en-US/gioi-thieu.html/` nhưng url_norm lưu `/en-us/gioi-thieu.html/`. Không mặc định hai HTTP resources này tương đương. Canonical mới giữ case; CSV nguồn/nhãn giữ nguyên, cảnh báo metadata không biến thành loại mẫu. Notebook legacy cũng không còn loại candidate chỉ vì khác metadata normalization này.

## B. Nguồn, bằng chứng, nhãn và ngữ cảnh Việt Nam

| Nguồn trong CSV | Nhãn đề xuất | n |
|---|---|---:|
| ACB official list of fake websites | phishing | 38 |
| Agribank official warning of spoofed domains | phishing | 6 |
| BIDV official consumer fraud warning | phishing | 4 |
| Bac Ninh government local public-service scam alert | phishing | 1 |
| NCSC warning republished by Dak Lak government | phishing | 44 |
| NCSC warning republished by Nghe An tech centre | phishing | 33 |
| NCSC weekly scam warnings on Ministry portal | phishing | 1 |
| Quang Ngai police publication of NCSC warning | phishing | 10 |
| VNCERT/CC warning on Ministry portal | phishing | 1 |
| aeon_official_corporate_profile | benign | 1 |
| government_portal | benign | 4 |
| official_business_site | benign | 18 |
| vnba_member_directory | benign | 6 |

Có 10 nhóm provenance sau khi gộp NCSC republications; vẫn chỉ một nhãn trong từng nhóm. 88 phishing là cảnh báo NCSC/republication, cùng cơ quan nguồn liên quan Core. Publisher URL mới không chứng minh feed/campaign độc lập. Không thực hiện leave-source-out hai lớp trên holdout chỉ có một nhãn, không lấy feed phishing + danh bạ benign rồi tuyên bố bias đã hết.

Mỗi candidate có source_reference, review_evidence, signature và kết quả kiểm tra tài liệu theo ID ở `candidate_audit.csv`. Kiểm tra HTTP/HTML tự động chỉ đọc reference chính thức allowlist; không theo hyperlink candidate. 99/167 hostname được tìm thấy nguyên chuỗi trong reference HTML sau xử lý dấu chấm vô hiệu hóa; HTML có thể chứa related links, ảnh/PDF/JS có thể không trích được. **Host mention không phải nhãn verified hoặc xác minh tình trạng hiện tại.** Chi tiết HTTP status, SHA256 tài liệu, thời điểm và giới hạn nằm ở `reports/annotations/k53_source_checks.csv`. Self-site reference không được coi là bằng chứng benign độc lập chỉ vì trang tự nhận chính thức.

### Review nội dung tài liệu và human check bổ sung

Sau bước availability/host mention, Codex đã đọc các đoạn cảnh báo và trường Website của hồ sơ hội viên VNBA, PDF corporate AEON (trang 6/10), giới hạn theo vị trí bài viết (không nhận related links/footer làm bằng chứng). `k53_reviews.csv` ghi quyết định cho đủ 167 ID; `k53_document_sources.csv` ghi SHA256 của bytes tài liệu thực đọc (HTML/PDF), thời điểm truy xuất, ngày/kỳ bài và locator. Kết quả: **99 verified theo tài liệu**, gồm 92 phishing và 7 benign; 68 pending. Ở thời điểm xuất snapshot PR #13 chưa có xác nhận human check. Hưng nay xác nhận kiểm tra lại cả 99 trường hợp; bản xác nhận riêng là căn cứ cho cách trình bày **human-checked** hiện tại. Method/reviewer trong ledger cũ phản ánh lần đối chiếu tài liệu ban đầu và không bị ghi đè; không diễn giải xác nhận mới thành một lần đánh giá độc lập hoặc kiểm tra website hiện tại.

Phạm vi verified chỉ là `hostname_historical`: hostname nguyên vẹn được nguồn cảnh báo chỉ rõ là giả mạo/lừa đảo, hoặc được hồ sơ tổ chức uy tín/tài liệu corporate của chủ sở hữu chỉ rõ là website của đơn vị. Nhãn phishing kế thừa là lớp cảnh báo giả mạo/lừa đảo rộng, không chứng minh mọi host đều đánh cắp credential; benign là danh tính tổ chức được ghi nhận, không bảo đảm không bị compromise hoặc mọi path đều an toàn. Không xác nhận trạng thái website hôm nay, không nâng lên full URL verified. Gate bắt buộc AI review có hash/locator/limitations và từ chối scope current/full URL.

Các trường hợp chưa đủ bằng chứng được giữ pending với lý do riêng: lỗi TLS nguồn Nghệ An (đã thử cả Python và curl dùng trust hệ điều hành), hostname có `www.` trong bài nhưng candidate đã bỏ tiền tố, reference danh bạ Chính phủ hiện trả homepage, và reference tự giới thiệu chưa có đối chiếu độc lập. Đặc biệt không mặc định `www.example` và `example` là cùng hostname/resource, không sửa raw URL hoặc nhãn để làm đủ số lượng. Các bằng chứng lịch sử không giải quyết source–label confounding; chỉ cho phép chuẩn bị recall pilot có phạm vi công bố rõ.

`brand_reference_cues` là tên key khớp trong reference hiện có, không xác minh chủ sở hữu, ý đồ hay việc tất cả brand là doanh nghiệp Việt Nam. Nguồn và warning nội dung Việt Nam hỗ trợ ngữ cảnh nhắm tới Việt Nam, nhưng không tạo mẫu ngẫu nhiên đại diện web Việt Nam. Hai lớp còn khác cơ chế tuyển chọn. collected_at vẫn thiếu, scraped_at chỉ ghi snapshot; không tự bịa ngày phát hiện hoặc trạng thái website hôm nay.

## C. Cohort ưu tiên được nhắc là “75 phishing”

Đã tìm lịch sử tất cả nhánh/commit liên quan external/pilot và phục hồi đúng bytes của `pilot_phishing_candidates.csv` tại commit `2a0765c7ab5a7fbcf38b3a25e0e45ddab3f81309`: **74 rows**, 75 dòng nếu tính cả header của file phishing. Không tìm thấy manifest chứng minh đúng 75 URL. Không thêm một URL giả hoặc tự gọi chúng verified. Bản phục hồi riêng có manifest mới ghi rõ nguồn Git, hash, số rows và danh sách ID ưu tiên; đây không phải manifest lịch sử được tìm thấy.

Cohort cũ gồm 74 phishing từ tinnhiemmang + 32 benign, tất cả pending. 29 hostname hiện tại trùng cohort cũ (đều benign trong snapshot này). Không gộp 106+167 thành số mẫu đánh giá độc lập, không trộn cohort cũ vào Core, Train hay cohort mới. Đối chiếu trong repository đã kết thúc ở **74 records / 75 lines kể header**; không coi một URL thứ 75 chưa có chứng cứ là blocker kỹ thuật hoặc tự tạo thêm. Nếu có cohort khác ngoài Git, phải nhận manifest thật trước khi đánh giá cohort đó.

## D. Biểu diễn và benchmark

Raw 15-cột không bị sửa. Ledger canonical nằm tại `data/external/derived/k53_candidates.csv`; `raw_url` giữ đúng URL được cung cấp, `normalized_url` không thêm scheme/path thiếu. `model_input_host` dùng hostname chuẩn của parser, còn subdomain, bỏ scheme/userinfo/port/path/query/fragment cho **cả hai lớp**. Đây là phép biến đổi mất thông tin, không tự bảo đảm label-preserving; cần review label ở scope hostname_historical/current. Host-only feature matrix đúng E2 v1, id + 20 features, không có metadata/labels trong X và không fit model.

Full-URL inventory có 29 URL HTTP(S) quan sát được nhưng 0 full URL verified; thiếu scheme không được điền http/https để giả thành dữ liệu thật. Benchmark full URL chỉ dùng khi URL và nhãn full-URL được review đúng scope. Shared external domain chỉ là audit flag; không tự xóa hoặc đổi nhãn. Input hostname trùng cần curation rõ trước chấm host-only, để không đếm lặp cùng representation.

Benchmark hiện **PREPARED / BLOCKED**: 99 host-only / 0 full-URL eligible và không có Teacher artifact finalized được cung cấp. `benchmark_status.json` ghi metrics=null, n_evaluated=0; exit 2 là blocked, không phải recall=0. Không có external metric thật, không có kết quả official.

Code khi đủ điều kiện chỉ gọi inference đã có, không train. Teacher lock cần hash bundle/selection record, lựa chọn bằng Core Train Group CV trước external, cùng feature order/schema/reference. Model metadata hiện có còn E2 v0; không gán weights v0 thành v1. Protocol Core hiện chốt estimator.predict, probability boundary .5 / margin 0; không có threshold mới chọn từ Core Validation. Yêu cầu “threshold cố định từ Validation” không được thực hiện bằng cách tune lại hoặc ghi provenance giả: giữ protocol hiện hành và đòi Teacher lock thực tế.

Mặc định chỉ báo recall trên phishing verified và theo từng nguồn; precision/F1/accuracy/FPR để null. `--two-class` cần hai lớp verified/eligible, chỉ tạo exploratory results, không tự nhận official/generalization. Nguồn holdout một lớp không được chạy leave-source-out hai lớp. Inference lỗi không được âm thầm bỏ row hoặc dùng model prediction làm nhãn đúng.

## E. Tái lập, kiểm thử và phần còn lại

Xem `data/external/README.md` cho data dictionary/lệnh, `verification.json` cho tests/Run All/hashes thực tế; không tính trạng thái chuẩn bị là benchmark đã chạy thành công. Audit có thể tái tạo offline, source checks là bước mạng tùy chọn. Review thật lưu riêng tại `reports/annotations/k53_reviews.csv`, có ID/signature/reviewer/time/evidence; không tự ghi tên người dùng hoặc human verification.

Chưa đủ tin cậy để báo cáo kết quả external chính thức. Phần audit đã tạo review có bằng chứng cho subset lịch sử, giữ pending các ID thiếu chứng cứ, và chốt đúng số bản ghi cohort cũ trong Git. Còn cần xác minh các nguồn/hostname pending và tuyển mẫu theo cùng cơ chế ở cả hai lớp để xử lý source–label confounding; không chỉ đổi tên nhóm nguồn hoặc tăng số URL. Phúc cần bàn giao Teacher đã khóa bằng Core-CV và bundle tương thích đúng version; sau đó mới chạy recall pilot trên subset đủ điều kiện và công bố giới hạn. Không hứa điểm tối đa hoặc đã loại leakage hoàn toàn.
