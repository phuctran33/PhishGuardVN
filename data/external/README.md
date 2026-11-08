# K5.3 external pilot — chưa phải ground truth chính thức

Hai CSV nguồn `phishing_candidates.csv` / `benign_candidates.csv` được giữ nguyên 15 cột, tổng 167 dòng (138/29), tất cả pending. Không đưa chúng vào train, tuning hoặc feature/model selection. Nhãn trong các tệp này là **đề xuất**, không phải nhãn lấy từ model hay ground truth đã chấp nhận.

## Tệp được tạo

| Tệp | Vai trò |
|---|---|
| `derived/k53_candidates.csv` | Ledger canonical 24 cột, giữ mọi ID/raw_url/label/status; không tự loại pending |
| `derived/k53_host_only_pilot.csv` | Input thử nghiệm host-only thống nhất hai lớp; chưa đủ điều kiện chấm metric |
| `derived/k53_full_url_inventory.csv` | Kiểm kê full URL quan sát được; có scheme không đồng nghĩa URL/nhãn đã verified |
| `derived/k53_host_only_features.csv` | `id` + đúng 20 features E2 v1 từ extractor chính thức; không có metadata/nhãn trong X |
| `derived/k53_host_only_feature_exclusions.csv` | ID không có representation hợp lệ, nếu có; không xóa row khỏi ledger |
| `history/2026-11-07/` | Bản phục hồi Git riêng: 74 phishing + 32 benign, đều pending; manifest ghi rõ không tìm được manifest đúng 75 URL |
| `../../reports/tables/external_pilot/candidate_audit.csv` | Tất cả audit flags/format/source checks/brand cues theo ID; không phải X |

Không ghép lịch sử 106 với snapshot 167 thành một external test mới: 29 benign trùng nhau; 74 phishing cũ từ `tinnhiemmang`. Không tự gán thêm URL thứ 75. Ưu tiên rà các ID lịch sử trong manifest, nhưng giữ trạng thái pending cho đến khi có bằng chứng.

## Data dictionary — canonical `k53-pilot-v1`

| Trường | Kiểu / ý nghĩa |
|---|---|
| `id`, `snapshot_id` | String; ID nguồn giữ nguyên, snapshot phân biệt cohort; nối theo ID trong đúng snapshot |
| `raw_url` | String **nguyên dạng giá trị `url` trong CSV nguồn**; không phải khẳng định là full URL chụp trực tiếp từ browser |
| `label` | `phishing` / `benign`; nhãn ứng viên kế thừa, chỉ trở thành ground truth trong phạm vi review được chấp nhận |
| `source`, `source_family` | Nguồn ghi nhận và nhóm provenance; NCSC republications gộp riêng, không gọi là feed độc lập |
| `source_reference` | `evidence_ref` nguồn; link/host mention không tự chứng minh nhãn |
| `review_status` | `verified`, `pending`, `rejected`; không tự chuyển trạng thái bằng dự đoán/brand/format |
| `review_evidence` | Căn cứ/giới hạn của nhãn; pending giữ review note gốc, không biến note chung thành xác nhận |
| `normalized_url` | Host chuẩn hóa theo parser, path/query giữ case, giữ scheme **chỉ nếu quan sát được**; không tự thêm `/` |
| `hostname`, `registrable_domain` | Host PSL/IDNA chính thức; domain không resolve được giữ rỗng và có lỗi, không tạo group giả |
| `model_input_host` | Host chuẩn hóa, giữ subdomain; bỏ scheme, port, userinfo, path/query/fragment cho **mọi** lớp. IPv6 có brackets để parser đọc đúng |
| `model_input_full` | URL HTTP(S) quan sát được; rỗng khi thiếu scheme. Chỉ dùng nếu scope/full_url_verified và các gate khác hợp lệ |
| `parse_valid`, `parse_error` | Boolean / mã lỗi parser; IP có thể hợp lệ nhưng không có registrable domain |
| `candidate_signature` | SHA256 của ID/raw_url/label/source/reference; review cũ bị từ chối nếu facts đổi |
| `reviewer`, `reviewed_at` | Danh tính người chịu trách nhiệm và thời điểm review ISO-8601; đang trống, không ghi tên người dùng tự động |
| `label_scope` | `unconfirmed`, `hostname_historical`, `hostname_current`, `full_url`; không mặc định chuyển label URL sang host |
| `full_url_verified` | Boolean; không thể có full-URL benchmark chỉ nhờ thêm scheme giả |
| `source_independence` | Ghi nhận review provenance; hiện `unresolved`, không tự gọi source-disjoint |
| `eligible_host_only`, `eligible_full_url` | Boolean gate **suy ra**, không thay review status. Pending/rejected/Core overlap/representation không hợp lệ không được chấm |

`candidate_audit.csv` giữ thêm metadata nguồn gốc, flags `core_overlap_*`, `legacy_overlap_*`, `shared_*`, `conflicting_labels_*`, đặc điểm format và nguồn kiểm chứng tài liệu. `normalized_url` giữ scheme quan sát; `comparison_url_key` bỏ scheme chỉ để kiểm tra overlap bảo thủ, không khẳng định HTTP/HTTPS tương đương. `shared_registrable_domain` không dẫn tới xóa row hoặc đổi nhãn; hostname trùng phải được xử lý rõ trước chấm host-only để tránh đếm lặp representation.

`stored_url_norm_mismatch` là cảnh báo metadata legacy: snapshot này có một URL Vexere mang path `en-US` nhưng url_norm cũ lưu `en-us`. Canonical giữ nguyên case của path; không tự sửa raw/nhãn hoặc loại row vì cảnh báo này. Audit phục hồi archive từ Git commit được ghi trong manifest, nên cần full Git history để tái tạo đúng nguồn cũ.

Các trường `source_document_status`, `reference_http_status`, `reference_body_sha256`, `source_host_seen`, `source_checked_at_utc`, `source_check_limit` ghi **AI-assisted document checks**, không phải human verification. HTML có thể chứa related links; không tìm thấy chuỗi host có thể do ảnh/PDF/JS. Brand cues chỉ là khớp reference string, không xác nhận danh tính hay độc hại.

## Tái lập

```bash
# Tùy chọn, có mạng: chỉ đọc reference chính thức đã allowlist; không theo link candidate.
python scripts/check_external_source_evidence.py
# Mặc định offline; giữ raw, mọi pending row và snapshot cũ.
python scripts/audit_external_pilot.py
# Hiện trả exit 2 = PREPARED/BLOCKED, metrics=null, không phải recall=0.
python scripts/evaluate_external_pilot.py
python -m pytest -q -rs
```

Review được lưu riêng tại `reports/annotations/k53_reviews.csv`, không sửa CSV nguồn; cột/ID/signature/evidence/time được kiểm tra. Không điền reviewer hoặc verified nếu chưa có review thật. Teacher lock mẫu ở `configs/external_teacher_lock.example.json` có `teacher_finalized=false`, không phải artifact đã được cung cấp. Thiếu Teacher đã chốt, nhãn phù hợp, feature version/reference hoặc hash thì phải dừng; không tự train hay thay v0 thành v1.

Mặc định benchmark chỉ báo recall phishing đã verified theo từng nguồn. `--two-class` chỉ tạo kết quả **exploratory**, cần cả hai nhãn verified hợp lệ; không tự gọi official và không chạy leave-source-out training. Protocol Core hiện có dùng estimator.predict, probability boundary 0.5 / margin 0; không chọn threshold từ external hoặc tune lại Validation. `scraped_at` trong CSV nguồn là thời điểm snapshot, không thay `collected_at` còn thiếu.
