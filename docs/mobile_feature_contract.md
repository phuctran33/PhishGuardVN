# Hợp đồng trích xuất đặc trưng E2 cho mobile (bản nháp)

**Schema:** `e2-brand-v1` · **Trạng thái:** bản nháp cho v0, đóng băng cùng bản v1 (reference đã xác minh).
**Nguồn chuẩn:** `src/phishguard_vn/url_parser.py`, `features.py`, `brand_features.py`. Khi tài liệu và code lệch nhau, code là đúng và tài liệu phải sửa.
**Kiểm chứng:** `docs/mobile_parity_cases.json` (sinh bằng `scripts/05_make_parity_vectors.py`). Một bản port chỉ được coi là khớp khi mọi ca khớp trong dung sai.

## 1. Đầu vào, đầu ra, thứ tự cột
- Đầu vào: một chuỗi URL (có thể thiếu scheme, rỗng hoặc null). Không truy cập mạng, không đọc nhãn/nguồn.
- Đầu ra: 20 số thực (float64), hoặc **trạng thái "không phân loại được"** kèm `error_reason` khi URL không hợp lệ (mục 8).
- Thứ tự cột cố định (12 lexical E1 giữ nguyên, 8 brand nối sau):

 1. `url_len`
 2. `dom_len`
 3. `is_ip`
 4. `subdom_cnt`
 5. `letter_cnt`
 6. `digit_cnt`
 7. `dot_cnt`
 8. `dash_cnt`
 9. `under_cnt`
10. `slash_cnt`
11. `entropy`
12. `path_len`
13. `brand_in_domain`
14. `brand_in_subdomain`
15. `brand_in_path`
16. `brand_domain_mismatch`
17. `brand_typo_score`
18. `susp_token_cnt`
19. `idna_flag`
20. `homoglyph_brand_hit`

## 2. Chuỗi xử lý (đúng thứ tự)
1. Cắt khoảng trắng hai đầu. Rỗng → `empty_url`; không phải chuỗi/null → `missing_url`.
2. Thêm scheme để phân tích: có `scheme://` (regex `^[a-zA-Z][a-zA-Z0-9+.-]*://`) → giữ nguyên; bắt đầu bằng `//` → thêm `http:`; còn lại → thêm `http://`.
3. Tách bằng cách `urlsplit` (không phải `urlparse`): path giữ nguyên `;params`, query tách riêng, userinfo bị bỏ (host là phần sau `@` cuối).
4. Port không hợp lệ → `invalid_port`. Host rỗng hoặc có khoảng trắng → `invalid_hostname`.
5. Chuẩn hóa host (mục 3). IP hợp lệ → URL hợp lệ, `is_ip=1`, không có registrable domain.
6. Tách registrable domain và subdomain bằng Public Suffix List (mục 3). Không có registrable domain → `unresolved_domain`.
7. Tính 12 lexical (mục 4), rồi 8 brand (mục 5 đến 7).

## 3. Chuẩn hóa host và PSL
- Bỏ `[` `]`, bỏ dấu chấm cuối. IPv4/IPv6 → dạng rút gọn chuẩn (IPv6 `2001:0db8:0:0:0:0:0:1` → `2001:db8::1`).
- Host chỉ có ký tự ASCII → chữ thường, **không** chạy IDNA (IDNA2008 từ chối `_`, mà URL thật hay dùng).
- Host có ký tự không phải ASCII → IDNA kiểu UTS46 sang Punycode, chữ thường. Lỗi → `invalid_hostname`.
- PSL: **snapshot đóng gói sẵn trong gói `tldextract` đúng phiên bản được ghi trong file parity** (không tải mạng, không cache), `include_psl_private_domains=False` (vd. mọi `*.weebly.com` → registrable `weebly.com`).
- Registrable domain = domain + suffix; **SLD = nhãn đầu của registrable domain**; subdomain = phần còn lại bên trái.

## 4. 12 đặc trưng lexical (E1)
`text` = URL đã bỏ scheme (và bỏ `//` đầu chuỗi nếu có), giữ nguyên chữ hoa/thường và mọi ký tự còn lại (path, query).
`url_len`=độ dài `text` · `dom_len`=độ dài registrable domain (URL là IP: độ dài chính địa chỉ IP đã chuẩn hóa) · `is_ip` · `subdom_cnt`=số nhãn ngăn bởi dấu chấm trong subdomain (0 nếu rỗng) · `letter_cnt` (ký tự chữ, Unicode) · `digit_cnt` · `dot_cnt` · `dash_cnt` · `under_cnt` · `slash_cnt` · `entropy`=Shannon log2 theo ký tự của `text` (chuỗi rỗng = 0) · `path_len`=độ dài path (từ bước 3, có `;params`, không có query).
Kiểu: tất cả là số thực, không có NaN/Inf với URL hợp lệ.

## 5. Chuẩn hóa chuỗi cho brand
- Gấp chuỗi: casefold → NFKD → `đ`→`d` → bỏ ký tự tổ hợp (dấu).
- Token: các cụm `[a-z0-9]+` liên tiếp sau khi gấp. `joined` = nối các token của một vùng, không có dấu cách.
- Ba vùng: **domain** = SLD (giải Punycode từng nhãn `xn--` trước khi gấp), **subdomain** (giải Punycode), **path** = path và query sau khi giải %-encoding (UTF-8).
- Key brand: tên chuẩn và alias của từng brand, gấp rồi bỏ mọi ký tự không phải chữ-số. Alias ngắn hơn 3 ký tự hoặc trùng STOPLIST bị từ chối khi nạp; alias trùng giữa hai brand báo lỗi.
- STOPLIST: `and`, `app`, `bank`, `bao`, `com`, `gov`, `hang`, `mobile`, `net`, `ngan`, `online`, `org`, `pay`, `shop`, `store`, `the`, `tin`, `viet`, `vietnam`, `vnn`, `web`, `www`.
- Khớp key trên một vùng: key dài ≥ 5 ký tự → là chuỗi con của `joined`; key ngắn hơn → trùng nguyên một token.

## 6. Tám đặc trưng brand
- `brand_in_domain` / `brand_in_subdomain` / `brand_in_path`: 1 nếu một key brand bất kỳ khớp ở vùng tương ứng.
- `brand_domain_mismatch`: 1 nếu có brand khớp ở một trong ba vùng, và registrable domain **không** thuộc `official_domains` của bất kỳ brand nào, và không thuộc ngoại lệ `official_suffixes` của chính brand đó (cột tùy chọn, mặc định rỗng; chỉ miễn trừ khi brand khớp DUY NHẤT ở subdomain và registrable domain kết thúc bằng suffix đó).
- `brand_typo_score`: duyệt token (độ dài ≥ 5) của SLD và subdomain mà **không** trùng key nào (kể cả brand khác) và không nằm trong `typo_ignore_tokens` của brand đó; với key dài ≥ 5 và chênh độ dài ≤ 2, tính khoảng cách OSA `d`. Nếu `1 ≤ d ≤ 2` và `d/len(key) ≤ 0.25` thì ứng viên điểm `1 − d/len(key)`; kết quả là điểm lớn nhất, không có thì 0. Bỏ qua nếu registrable domain là domain chính thức của một brand bất kỳ.
- `susp_token_cnt`: số từ khóa KHÁC NHAU trong danh sách dưới đây khớp ở bất kỳ vùng nào (cùng quy tắc khớp như key brand): `login`, `signin`, `verify`, `secure`, `security`, `account`, `update`, `confirm`, `wallet`, `otp`, `bonus`, `gift`, `promo`, `refund`, `support`, `helpdesk`, `ebanking`, `internetbanking`, `payment`, `billing`, `dangnhap`, `xacminh`, `xacthuc`, `taikhoan`, `baomat`, `capnhat`, `khuyenmai`, `uudai`, `trungthuong`, `nhanqua`, `hoantien`, `thanhtoan`, `hotro`.
- `idna_flag`: 1 nếu một nhãn của hostname đã chuẩn hóa bắt đầu bằng `xn--`.
- `homoglyph_brand_hit`: 1 nếu key brand KHÔNG khớp thô ở domain hoặc subdomain nhưng khớp sau khi gộp ký tự dễ nhầm (cả key lẫn chuỗi), và registrable domain không phải domain chính thức của brand nào.

OSA = khoảng cách Levenshtein cộng hoán vị hai ký tự liền kề (optimal string alignment).

## 7. Gộp ký tự dễ nhầm
Áp dụng theo thứ tự: nhiều ký tự trước (`rn`→`m`, `vv`→`w`), rồi từng ký tự (`0`→`o`, `1`→`l`, `i`→`l`, `3`→`e`, `4`→`a`, `5`→`s`, `7`→`t`, `8`→`b`). Phải áp dụng đối xứng cho cả key brand lẫn chuỗi cần so.

## 8. URL không hợp lệ
Mã lỗi: `missing_url`, `empty_url`, `invalid_port`, `invalid_hostname`, `unresolved_domain`, `parsing_error:<Loại>`. Với các URL này **không** có vector đặc trưng và bản mobile không được trả số giả (0 hoặc NaN). Bản mobile phải trả trạng thái "không phân loại được" với `error_reason`, và không được văng lỗi. URL là IP hợp lệ **có** vector đặc trưng.

## 9. Kiểu số và dung sai
float64 ở Python; bản mobile có thể dùng float32 nếu dung sai tuyệt đối ≤ `1e-6` cho cột liên tục (`entropy`, `brand_typo_score`) và **bằng nhau tuyệt đối** cho cột đếm/cờ.

## 10. Rủi ro khi port (cần kiểm trước)
1. **PSL:** phải dùng đúng snapshot của phiên bản `tldextract` đã ghi; PSL khác phiên bản cho registrable domain khác, kéo theo `dom_len` và mọi brand feature.
2. **IDNA:** Python (gói `idna`, UTS46) và thư viện của Android/iOS có thể khác nhau với ký tự đặc biệt. Chỉ hứa khớp trên các ca trong file parity.
3. **Unicode:** NFKD, casefold và danh sách ký tự tổ hợp phải cho kết quả như Python; kiểm với các ca có dấu tiếng Việt.
4. **Regex/ký tự:** `isalpha`/`isdigit` của Python là Unicode; kiểm các ký tự không phải ASCII trong path.
5. **urlsplit:** hành vi với userinfo, `;params`, port lỗi, IPv6 phải khớp từng ca.
6. **Hash reference:** bản port phải mang cùng `brand_reference.sha256` ghi trong file parity.

## 11. Đổi version
Đổi bất kỳ tham số, danh sách, bảng gộp ký tự, brand reference hay phiên bản PSL nào = đổi `FEATURE_SCHEMA_VERSION` (hoặc ghi hash mới), sinh lại file parity và báo Phúc/Hưng chạy lại các thí nghiệm liên quan.