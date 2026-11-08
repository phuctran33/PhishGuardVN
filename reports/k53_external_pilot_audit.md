# K5.3 — External pilot audit và benchmark readiness

## A. Audit trước và sau

| Kiểm tra | Trước (CSV nguồn) | Sau audit / chuẩn hóa |
|---|---:|---:|
| Candidates | 167 | 167, giữ toàn bộ ID/raw_url/label |
| Phishing / benign | 138 / 29 | Không đổi nhãn |
| Verified / pending / rejected | 0 / 167 / 0 | 0 / 167 / 0 |
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

`brand_reference_cues` là tên key khớp trong reference hiện có, không xác minh chủ sở hữu, ý đồ hay việc tất cả brand là doanh nghiệp Việt Nam. Nguồn và warning nội dung Việt Nam hỗ trợ ngữ cảnh nhắm tới Việt Nam, nhưng không tạo mẫu ngẫu nhiên đại diện web Việt Nam. Hai lớp còn khác cơ chế tuyển chọn. collected_at vẫn thiếu, scraped_at chỉ ghi snapshot; không tự bịa ngày phát hiện hoặc trạng thái website hôm nay.

## C. Cohort ưu tiên được nhắc là “75 phishing”

Đã tìm lịch sử tất cả nhánh/commit liên quan external/pilot và phục hồi đúng bytes của `pilot_phishing_candidates.csv` tại commit `2a0765c7ab5a7fbcf38b3a25e0e45ddab3f81309`: **74 rows**, 75 dòng nếu tính cả header của file phishing. Không tìm thấy manifest chứng minh đúng 75 URL. Không thêm một URL giả hoặc tự gọi chúng verified. Bản phục hồi riêng có manifest mới ghi rõ nguồn Git, hash, số rows và danh sách ID ưu tiên; đây không phải manifest lịch sử được tìm thấy.

Cohort cũ gồm 74 phishing từ tinnhiemmang + 32 benign, tất cả pending. 29 hostname hiện tại trùng cohort cũ (đều benign trong snapshot này). Không gộp 106+167 thành số mẫu đánh giá độc lập, không trộn cohort cũ vào Core, Train hay cohort mới. Trạng thái yêu cầu 75-vs-74 còn **UNRESOLVED** để chủ dữ liệu đối chiếu nếu có manifest khác ngoài Git.

## D. Biểu diễn và benchmark

Raw 15-cột không bị sửa. Ledger canonical nằm tại `data/external/derived/k53_candidates.csv`; `raw_url` giữ đúng URL được cung cấp, `normalized_url` không thêm scheme/path thiếu. `model_input_host` dùng hostname chuẩn của parser, còn subdomain, bỏ scheme/userinfo/port/path/query/fragment cho **cả hai lớp**. Đây là phép biến đổi mất thông tin, không tự bảo đảm label-preserving; cần review label ở scope hostname_historical/current. Host-only feature matrix đúng E2 v1, id + 20 features, không có metadata/labels trong X và không fit model.

Full-URL inventory có 29 URL HTTP(S) quan sát được nhưng 0 full URL verified; thiếu scheme không được điền http/https để giả thành dữ liệu thật. Benchmark full URL chỉ dùng khi URL và nhãn full-URL được review đúng scope. Shared external domain chỉ là audit flag; không tự xóa hoặc đổi nhãn. Input hostname trùng cần curation rõ trước chấm host-only, để không đếm lặp cùng representation.

Benchmark hiện **PREPARED / BLOCKED**: 0 host-only / 0 full-URL eligible và không có Teacher artifact finalized được cung cấp. `benchmark_status.json` ghi metrics=null, n_evaluated=0; exit 2 là blocked, không phải recall=0. Không có external metric thật, không có kết quả official.

Code khi đủ điều kiện chỉ gọi inference đã có, không train. Teacher lock cần hash bundle/selection record, lựa chọn bằng Core Train Group CV trước external, cùng feature order/schema/reference. Model metadata hiện có còn E2 v0; không gán weights v0 thành v1. Protocol Core hiện chốt estimator.predict, probability boundary .5 / margin 0; không có threshold mới chọn từ Core Validation. Yêu cầu “threshold cố định từ Validation” không được thực hiện bằng cách tune lại hoặc ghi provenance giả: giữ protocol hiện hành và đòi Teacher lock thực tế.

Mặc định chỉ báo recall trên phishing verified và theo từng nguồn; precision/F1/accuracy/FPR để null. `--two-class` cần hai lớp verified/eligible, chỉ tạo exploratory results, không tự nhận official/generalization. Nguồn holdout một lớp không được chạy leave-source-out hai lớp. Inference lỗi không được âm thầm bỏ row hoặc dùng model prediction làm nhãn đúng.

## E. Tái lập, kiểm thử và phần còn lại

Xem `data/external/README.md` cho data dictionary/lệnh, `verification.json` cho tests/Run All/hashes thực tế; không tính trạng thái chuẩn bị là benchmark đã chạy thành công. Audit có thể tái tạo offline, source checks là bước mạng tùy chọn. Review thật lưu riêng tại `reports/annotations/k53_reviews.csv`, có ID/signature/reviewer/time/evidence; không tự ghi tên người dùng hoặc human verification.

Chưa đủ tin cậy để báo cáo kết quả external chính thức. Cần chủ dữ liệu giải quyết cohort 75-vs-74, review nhãn và scope của các nguồn cảnh báo lịch sử, ownership/đích benign và evidence không truy xuất được; cần tuyển mẫu/thiết kế provenance để xử lý source–label confounding ở cả hai lớp, không chỉ tăng số URL. Phúc cần bàn giao Teacher đã khóa bằng Core-CV và bundle tương thích đúng version; sau đó mới chạy recall pilot với đủ support và công bố giới hạn. Không hứa điểm tối đa hoặc đã loại leakage hoàn toàn.
