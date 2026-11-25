# Tuần 8–9 · Bàn giao Web, Chrome và Brand Detector (#38)

## Phạm vi và tích hợp

Base `16c9c24072bc73628eae905256021eb24dfb4aa4` sau PR #32, #35 và #33.
QR, Brand Detector và X-Ray tuần 7 đến từ #32. PR #35 bàn giao Student MLP KD int8
cho phạm vi Android. PR #34 đang mở ở thời điểm audit và thuộc QA của Khiêm.
Phần #36 chưa có endpoint, fixture bàn giao hoặc PR trên các nhánh công khai
đã kiểm tra. [Issue #38](https://github.com/phuctran33/PhishGuardVN/issues/38) ·
[Issue #36](https://github.com/phuctran33/PhishGuardVN/issues/36) ·
[PR #34](https://github.com/phuctran33/PhishGuardVN/pull/34)

- **Teacher** trả nhãn qua `POST /predict` cho Web và Chrome. QR trên Web decode
  từ ảnh tại máy, chờ xác nhận rồi mới gửi URL. Extension MV3 gửi link đã chọn
  từ menu chuột phải và giữ URL trong bộ nhớ đến khi đóng cửa sổ.
- **Brand Detector và X-Ray** dùng `POST /inspect`. Parser và 45 thương hiệu cũ
  vẫn làm mốc quy tắc. Module inspection nạp các bổ sung đã xác minh từ tài
  nguyên package, lập bảng tra domain và alias ở startup rồi tái sử dụng.
- **Ca phishing tương tự** có adapter, panel độc lập và fixture đề xuất #36,
  với giới hạn 5 ca, plain text, nguồn, cosine, highlight theo Unicode, empty,
  timeout và retry. Response chứa userinfo, query chưa che hoặc range sai bị
  từ chối. Khi chưa có endpoint, Web báo chưa sẵn sàng. GitHub #36 cần bàn giao
  schema, corpus, mẫu có/không kết quả và endpoint thật để chạy E2E dương tính.
  [Contract](../docs/api_contract.md) · [Web](../apps/web/README.md) · [Chrome](../apps/extension/README.md)

## Phạm vi Việt Nam và nguồn xác minh

Đối chiếu ngày **24/11/2026**. Danh mục chỉ nhận tổ chức Việt Nam hoặc thương hiệu
quốc tế có căn cứ hoạt động hoặc phổ biến tại Việt Nam. Mỗi dòng bổ sung có
`vietnam_scope`, `vietnam_scope_source_url` và `vietnam_scope_evidence` bên cạnh
thông tin website, nguồn domain, ngành, khu vực, ngày kiểm và trạng thái.
`verified` ghi nhận đối chiếu bằng tài liệu công bố. Căn cứ thuộc phạm vi được
lưu riêng với bằng chứng domain khi hai nguồn khác nhau.

| Phạm vi | Brand |
|---|---:|
| `vietnamese` | 1.864 |
| `international_operating_in_vietnam` | 107 |
| `international_popular_in_vietnam` | 5 |

`vietnamese` gồm pháp nhân, cơ sở và cơ quan có danh tính tại Việt Nam.
Nhóm quốc tế hoạt động cần nguồn ghi dịch vụ tại Việt Nam, chi nhánh, thành
viên thị trường hoặc tuyến khai thác trong nước. Nhóm quốc tế phổ biến cần
số liệu gắn với Việt Nam. Ví dụ Statcounter phân tách thị phần tìm kiếm tại
Việt Nam, GitHub có trang số liệu nhà phát triển Việt Nam, còn Digital 2026
có chỉ số tiếp cận Facebook, YouTube và TikTok ở Việt Nam. Dùng chỉ số đối
chiếu mức độ hiện diện. Danh mục không chuyển chỉ số tiếp cận quảng cáo
thành số người dùng hoạt động. [Statcounter Việt Nam](https://gs.statcounter.com/search-engine-market-share/all/viet-nam) ·
[GitHub Innovation Graph: Vietnam](https://innovationgraph.github.com/economies/vn) ·
[Digital 2026: Vietnam](https://datareportal.com/reports/digital-2026-vietnam)

| Lô nguồn | Dòng đã rà | Dòng domain nhận | Trùng | Chờ xác minh | Ngoài phạm vi |
|---|---:|---:|---:|---:|---:|
| Đối chiếu có chọn lọc | 13 | 13 | 0 | 0 | 0 |
| Trang first-party, lượt đầu | 181 | 106 | 0 | 45 | 30 |
| Trang first-party, lượt bổ sung | 146 | 84 | 4 | 58 | 0 |
| Cổng Chính phủ | 51 | 42 | 8 | 1 | 0 |
| HNX, trang công khai đầu | 10 | 8 | 2 | 0 | 0 |
| Hiệp hội Thị trường Trái phiếu | 24 | 13 | 10 | 1 | 0 |
| Cảng hàng không Nội Bài | 52 | 43 | 1 | 8 | 0 |
| VINASA, danh bạ theo địa phương | 301 | 287 | 6 | 8 | 0 |
| VLA, 38 trang danh bạ | 236 | 224 | 5 | 7 | 0 |
| Bộ Y tế, 128 trang danh sách | 1.273 | 993 | 32 | 248 | 0 |
| Hiệp hội Ngân hàng Việt Nam | 43 | 20 | 21 | 2 | 0 |
| FIATA, hồ sơ thành viên Việt Nam | 136 | 100 | 32 | 4 | 0 |
| **Tổng các lô đã rà theo phạm vi Việt Nam** | 2.466 | 1.933 | 121 | 382 | 30 |

Các lô FDIC, UK Finance và IATA toàn cầu của lượt thu thập trước chỉ còn
thống kê loại trừ. Dùng nguồn Nội Bài thay cho suy đoán hãng bay có hoạt động
tại Việt Nam. Tổng số dòng loại theo phạm vi là **4.582**, gồm cả
trang first-party quốc tế thiếu căn cứ tại Việt Nam. Ba nhóm quốc tế ở v1
(Shopee, Lazada, J&T Express) được phân nhóm theo hồ sơ đã có trong v1.
[Ledger lô nguồn](tables/week8_9/catalog_sources.csv) · [Ứng viên chờ](tables/week8_9/catalog_exclusions.csv)

### Kiểm nguồn và chuẩn hóa

- Cổng Chính phủ liệt kê website trong hồ sơ 34 tỉnh/thành cùng hồ sơ bộ/ngành.
  Bộ Y tế công bố tên đơn vị và cột website trong danh sách bệnh án điện tử.
  Đọc đủ 128 trang theo phân trang công khai. HNX/VBMA và VNBA có tên và website
  thành viên. Với HNX lấy các dòng hiển thị trong trang công khai đầu, đủ
  bằng chứng cho phần nạp đã ghi. [Cổng Chính phủ](https://chinhphu.vn/po) ·
  [Bộ Y tế](https://benhandientu.moh.gov.vn/) · [HNX](https://cbonds.hnx.vn/danh-sach-thanh-vien) ·
  [VBMA](https://vbma.org.vn/vi/membership/official) ·
  [VNBA](https://vnba.org.vn/vi/vnba/member)
- Tra trường Website ở VINASA, VLA và FIATA mục Việt Nam. Trang Nội Bài ghép
  tên hãng và website liên hệ theo một thẻ hãng. Với nhóm thương hiệu ưu tiên
  ngoài danh bạ, kiểm tên trong trang first-party, trang khu vực hoặc nguồn
  công ty mẹ. Ví dụ MWG nêu Thế Giới Di Động và website của chuỗi.
  [VINASA](https://www.vinasa.org.vn/vinasa/4/3074/4281/hoi-vien-ha-noi/) ·
  [VLA](https://vla.com.vn/danh-ba-hoi-vien/) · [FIATA Việt Nam](https://fiata.org/directory/vn/) ·
  [Nội Bài](https://noibaiairport.vn/vi/flights/airlines) ·
  [MWG](https://mwg.vn/gioi-thieu)
- Việc nạp dùng parser và IDNA, kiểm registrable domain bằng PSL offline.
  Chỉ lấy root hoặc hostname `www` được ghi nhận. Hồ sơ dùng subdomain
  riêng của nền tảng, domain dùng chung giữa nhiều pháp nhân, URL không đủ
  căn cứ và bản ghi trùng tên nhiều root được tách ra tra sau. Trong trường
  hợp có bằng chứng first-party đánh giá root của nền tảng, chỉ ghi nhận
  danh tính nền tảng. Tách quá trình đối chiếu nguồn khỏi runtime. Dataset
  đã gán nhãn, Official Test và external test nằm ngoài quá trình lựa chọn.
- Alias v2 chỉ bật dạng đã tuyển chọn theo ranh giới token, chữ hoa/thường
  và dấu tiếng Việt quy về cùng dạng. Alias không nối xuyên query param hoặc
  path segment. Tên phổ thông như Apple và tên ngắn như VTV nhận theo domain
  trong danh mục. MISA và Honda dùng cụm đầy đủ để giảm nghĩa trùng.
  Hai domain NAPAS và VietQR có hồ sơ riêng thường trực nhưng tính một brand.
  [NAPAS xác nhận VietQR](https://en.napas.com.vn/napas-fastfund-247-with-vietqr-code-service)

| Phiên bản | Thương hiệu / tổ chức | Domain | Dạng alias |
|---|---:|---:|---:|
| Reference v1 | 45 | 55 | 58 |
| Bổ sung v2 | 1.931 | 1.933 | 189 |
| **Inspection thực tế** | 1.976 | 1.988 | 247 |

58 dạng v1 gồm tên chính đã normalize. Dạng v2 là các alias được bật.
34 nhóm ngành gồm cả cơ quan Trung ương và 34 cổng địa phương. Y tế và logistics
chiếm tỷ trọng lớn do danh bạ ngành có trường website. Khu vực trong hồ sơ
gồm VN 1.901 · International 40 · US 13 · JP 4 · SG 4 · CN 3 · KR 3 · TH 2 · DE 1 · GB 1 · HK 1 · ID 1 · IT 1 · TW 1. VN ở trường khu vực bao gồm cả hồ sơ chi nhánh tại Việt Nam,
vì vậy dùng `vietnam_scope` khi đếm theo loại liên hệ với Việt Nam.

| Ngành | Brand | Ngành | Brand |
|---|---:|---|---:|
| automotive | 9 | healthcare | 998 |
| aviation | 45 | hospitality | 3 |
| bank | 38 | insurance | 11 |
| construction | 1 | investment | 1 |
| consumer_goods | 9 | media | 11 |
| cosmetics | 1 | payments | 9 |
| delivery | 333 | pharmacy | 3 |
| ecommerce | 3 | real_estate | 8 |
| education | 28 | retail | 13 |
| employment | 6 | securities | 12 |
| entertainment | 5 | social | 3 |
| ewallet | 3 | software | 293 |
| fashion | 6 | technology | 10 |
| financial_services | 23 | telecom | 7 |
| food | 11 | transport | 4 |
| gov | 24 | travel | 4 |
| gov_local | 34 | utility | 7 |

SHA-256 CSV mở rộng `84629d25f71d19a7292a1b9dcf3270ee834c9b8664bd9a3a725209b388fb6265`. Manifest kiểm checksum, các cột
phạm vi Việt Nam và số đếm. Tài nguyên CSV/manifest được đóng gói trong wheel.
[Manifest theo ngành và khu vực](../src/phishguard_vn/resources/brand_catalog_v2.manifest.json)

## Benchmark Brand Detector trong bối cảnh Việt Nam

Cùng fixture cố định gồm **102 ca**, 98
ca parse được và 4 đầu vào lỗi. Ground truth gồm set brand, official match
và mismatch theo brand. Bộ ca gồm domain bộ/ngành, địa phương, y tế, giáo
dục, ngân hàng, công ty Việt Nam và thương hiệu quốc tế đang khai thác ở
Việt Nam. Có tiếng Việt có dấu/không dấu, chữ viết tắt VCB, PTIT, VIB,
Unicode/IDNA, IP và tên trùng ngữ cảnh. Mẫu số negative là
22 ca unrelated và ambiguous names.

| Chỉ số | Reference 45 | Danh mục Việt Nam mở rộng |
|---|---:|---:|
| Đúng đủ brand / official / mismatch | 46/102 | 96/102 |
| TP / FP / FN theo cặp (ca, brand) | 19 / 1 / 57 | 71 / 1 / 5 |
| Precision | 95,00% | 98,61% |
| Recall | 25,00% | 93,42% |
| F1 | 39,58% | 95,95% |
| Ca gắn nhầm | 1 | 1 |
| FPR nhóm negative | 1/22 | 1/22 |
| Đúng thêm / gắn nhầm thêm / đúng cũ thành sai | mốc gốc | +50 / 0 / 0 |
| Ca cả hai bản bỏ sót toàn bộ brand kỳ vọng | 5 | 5 |
| Latency hàm inspection p50 / p95 (ms) | 0,106 / 0,162 | 0,124 / 0,201 |
| Nạp dữ liệu (ms) | 0,574 | 146,777 |

Đo 1.960 lần mỗi nhánh trên macOS arm64, CPython
3.11.17, sau warm-up và luân phiên thứ tự chạy. Nạp đo một lần ở process
mới. Benchmark tính nhận diện tên/domain, với typo/homoglyph là tín hiệu yếu.
Đây là kết quả trên fixture inspection có chủ đích, không phải chỉ số
phân loại phishing hay ước lượng hiệu quả Teacher trên dữ liệu triển khai.

- E77 gắn nhầm Tiki trong ngữ cảnh bóng đá `tiki-taka` ở cả hai bản vì alias
  cũ. E81–E85 là năm ca cả hai bỏ sót với tên phổ thông, tên ngắn hoặc
  từ nối ngoài dạng alias đã xét. E82 chứa tên Bảo Minh thiếu cụm ngành
  được duyệt và E102 đối chiếu ngữ cảnh khác với cụm từ tương tự.
- E42–E43 kiểm một domain chính thức trong catalog không triệt tín hiệu
  brand khác khi brand đó xuất hiện. E94 và E95 kiểm VCB và PTIT. E97/E98
  so tên đại học có dấu/không dấu. Các ca đuôi không phải .vn bao gồm
  hãng bay, logistics và ứng dụng quốc tế có nguồn về Việt Nam.
  [Fixture](../tests/fixtures/brand_catalog_eval.csv) ·
  [Từng ca](tables/week8_9/brand_benchmark_cases.csv) ·
  [Mẫu số từng nhóm và timing](tables/week8_9/brand_benchmark.json)

## Bảo toàn Teacher

So lại cùng 12 request tại base và bản tích hợp bằng release loader thật.
**12/12 phản hồi khớp**, gồm 10 URL hợp lệ và 2 URL bị từ chối. Sai khác score
tối đa **0** với tolerance `1e-12`. Ma trận E2 10 hàng × 20 cột khớp từng giá trị,
kèm feature order, phiên bản, rule `score >= threshold` và ngưỡng
`0.6945740700635259`. Kiểm checksum bundle, hai lock, bốn extractor source đã pin,
reference v1 và Student MLP artifact. Bundle Teacher có SHA-256
`63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`.
[Parity và SHA trước/sau](tables/week8_9/teacher_parity.json)

## Tái lập và tự kiểm

Lần clean clone dùng Git branch với depth 1, venv CPython 3.11.17 mới, cài
`requirements-teacher.txt` và các extras dưới đây. Kiểm thêm wheel để xác nhận
đóng gói cả CSV reference v1, CSV mới và manifest JSON. Flutter **3.47.9**
và Dart **3.13.7**.

```sh
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-teacher.txt -e '.[api,test,teacher,research]'
python -m pip check
OMP_NUM_THREADS=1 MPLBACKEND=Agg python -m pytest -p no:cacheprovider -q -rs \
  --teacher-root=. --teacher-api -k 'not test_real_external_bundle_matches_saved_scores'
python scripts/verify_brand_catalog.py
python scripts/benchmark_brand_catalog.py --out /tmp/pgvn-brand-benchmark
node --test apps/extension/tests/*.test.mjs
(cd apps/web && flutter pub get && flutter analyze && flutter test)
```

Sau một thay đổi dữ liệu đã kiểm, `python scripts/verify_brand_catalog.py
--write-manifest` tái tạo manifest từ CSV. Để kiểm parity từ gốc, tạo worktree
tại base, gọi `scripts/verify_week8_teacher_boundary.py --root PATH_TO_BASE
--out /tmp/teacher-base.json` rồi gọi script từ checkout cần kiểm với
`--compare /tmp/teacher-base.json --out /tmp/teacher-paired.json`.

Demo thường dùng FastAPI **8000**, Web **3000**. Lượt kiểm tự động dùng FastAPI
**18380** và Web **3308**. Script dùng Chromium headless, không điều khiển
màn hình. Với Extension, script cài một bản tạm và truyền link từ fixture
vào callback của service worker. Cửa sổ kết quả và API chạy thật. Chạy menu
chuột phải được ghi nhận riêng trong Chrome for Testing có cửa sổ.
Script khởi động và dừng các tiến trình demo do script tạo.

```sh
(cd apps/web && flutter build web --release --no-web-resources-cdn \
  --dart-define=API_BASE_URL=http://127.0.0.1:18380)
npm install --prefix /tmp/pgvn-browser-tools playwright@1.65.1
/tmp/pgvn-browser-tools/node_modules/.bin/playwright install chromium
NODE_PATH=/tmp/pgvn-browser-tools/node_modules \
  PGVN_PYTHON="$PWD/.venv/bin/python" PGVN_EVIDENCE_DIR=/tmp/pgvn-browser-evidence \
  node scripts/qa_week8_browser.cjs
```

Để kiểm menu native trên máy demo, dùng bước Load unpacked và thao tác chuột
phải bằng tay theo hướng dẫn Extension. [Chạy FastAPI](../docs/backend.md) ·
[Chạy Flutter Web](../apps/web/README.md) · [Cài Extension](../apps/extension/README.md)

## Trạng thái từng hạng mục Issue #38

| Mốc | Yêu cầu | Trạng thái và bằng chứng |
|---|---|---|
| Tuần 8 | MV3, menu chuột phải, hostname, nhãn, engine | Đã triển khai và thử trong Chrome for Testing với backend Teacher. |
| Tuần 8 | Bản unpacked, cấu hình backend và luồng lỗi | Có source cài trực tiếp, hướng dẫn localhost, UI thiết lập và ca lỗi. |
| Tuần 8 | Khối ca tương tự, nguồn, tô sáng, tối đa 5 | Đã chạy unit/widget với fixture được đánh dấu. Đối chiếu schema thật còn chờ #36. |
| Tuần 8 | Giao Hy mốc UI Web | Có bảng UI, ảnh browser thật và URL/QR fixture dùng chung ở phần dưới. |
| Tuần 8 | Schema, xác minh lô đầu và gửi ca QA | Có CSV, scope/source theo dòng, manifest, thống kê và bộ fixture dưới đây. |
| Tuần 8 | Demo Chrome với Teacher thật, bàn giao Khiêm | Có nhãn benign/phishing do Teacher thật trả, smoke record và hướng dẫn tái lập. |
| Tuần 9 | Nối API Similar Cases của Phúc và kiểm luồng đầy đủ | Chờ endpoint và dữ liệu bàn giao từ #36. Đã chạy trường hợp HTTP 404 trên Web release. |
| Tuần 9 | Danh mục lớn theo bối cảnh Việt Nam | Có nguồn, ngành, vùng, ngày kiểm và scope. Số lượng tính từ dữ liệu được nạp. |
| Tuần 9 | Nạp danh mục riêng vào /inspect | Provenance và fallback có schema/tự kiểm. Teacher API có parity cùng artifact. |
| Tuần 9 | Đo đúng/gắn nhầm, regression, phối hợp Khiêm | Đã chạy benchmark và bàn giao fixture, SHA, hướng dẫn qua PR. QA độc lập theo #39 chờ Khiêm. |

### Bàn giao UI cho Hy theo #37

| Luồng Web | Thông tin chính | Trạng thái dùng chung | Ca đối chiếu |
|---|---|---|---|
| Nhập URL | Trường URL và nút Kiểm tra URL | Rỗng, URL lỗi, nhập lại, giữ focus khi đổi selection | `example.com`, `https://example.com:bad/path` |
| Quét QR ảnh | Preview URL, Xác nhận và phân tích, Hủy | Đọc ảnh local, ảnh hỏng, thiếu QR, nội dung không phải URL, chờ duyệt | [Fixture PNG](../apps/web/test/fixtures/qr_url.png), [ảnh hỏng](../apps/web/test/fixtures/broken.png), [ảnh không có QR](../apps/web/test/fixtures/no_qr.png) |
| Kết quả phân loại | Nhãn API, tên engine, điểm và ngưỡng | Teal và chú thích ở benign, cảnh báo đỏ và chữ ở phishing, retry khi mất backend | `https://www.vietcombank.com.vn/` |
| Brand Detector | Nhãn quy tắc, brand, domain tham chiếu, vị trí bằng chứng, phiên bản danh mục | Chưa nhận diện, mismatch, ghi rõ khi dùng reference gốc | `https://napas.com.vn/`, `https://napas.com.vn/vietcombank` |
| URL X-Ray | Hostname, registrable domain, subdomain, path, IDNA | Xử lý IP, phần vắng và URL lỗi | `https://bücher.de/Path`, `http://192.0.2.1/` |

Web dùng danh mục Việt Nam mở rộng cho `/inspect` và Teacher stacking v2 cho
nhãn. Android tiếp tục dùng reference offline theo artifact của Hy. So
trường và trạng thái, ghi engine và phiên bản danh mục khi so số liệu.
[Issue #37](https://github.com/phuctran33/PhishGuardVN/issues/37)

### Bàn giao cho Phúc và Khiêm

Phúc có [schema Web và fixture đề xuất](../docs/api_contract.md#post-similar-cases--hợp-đồng-đề-xuất-cho-36).
Khi có bàn giao từ #36, cần replay ít nhất một truy vấn thật có ca phù hợp,
một truy vấn rỗng, một truy vấn lỗi/trùng, đồng thời so nguồn và range đã che
với response. Khiêm có bản unpacked, benchmark 102 ca đã lưu kỳ vọng, manifest,
ảnh Chrome và Web, lệnh clone/build, lệnh parity và biên bản trạng thái.
[Issue #39](https://github.com/phuctran33/PhishGuardVN/issues/39) ·
[Fixture 102 ca](../tests/fixtures/brand_catalog_eval.csv)

### Kết quả chạy

| Kiểm tra | Kết quả |
|---|---|
| Python full suite trong clone sạch | 674 passed, 0 failed, 2 skipped, 1 deselected. |
| Teacher API acceptance | 15 passed, 0 failed. Selector theo marker loại 17 ca ngoài gate. |
| Flutter 3.47.9 / Dart 3.13.7 | Pub get đạt. Analyze sạch. 55 passed, 0 failed. Build Web release đạt. |
| Node 24.18.0 | 10 passed, 0 failed. |
| Chromium headless | 26/26 smoke checks đạt trên Web release và Extension. |
| Teacher trước/sau | 12/12 HTTP khớp, 10/10 dòng E2 khớp, max score diff 0. |
| Wheel | CSV mới, manifest và reference gốc khớp checksum trong wheel. |
| Benchmark chạy lại | CSV kết quả từng ca giống từng byte, metrics khớp. Timing đo độc lập theo tải máy. |

Hai skip là bộ tham số brand regression cũ rỗng và handoff notebook 02/03
chỉ có ở môi trường đã chạy notebook. Deselection là
`test_real_external_bundle_matches_saved_scores` theo lệnh QA, tránh chấm
external ở lượt triển khai. Bốn warning từ suite hiện có. CPython **3.11.17**,
macOS **14.6.1 arm64**. QA mới chạy benchmark Brand Detector ngoài các tập
nghiên cứu.

Verifier lịch sử `05_verify_e2_artifacts.py` trên base và nhánh sạch đều **33/36**. Hai
kiểm tra diff của manifest coi thay đổi README/workflow từ SHA freeze cũng
là stale. Kiểm thứ ba so JSON E2 parity bằng đẳng thức tuyệt đối. Trên
runtime này 25 số entropy lệch tối đa `1,776×10⁻¹⁵` so với file lưu.
Các check này có sẵn ở base. Kiểm parity trước/sau của PR dùng cùng runtime
và đối chiếu đủ file đã hash. Hai ma trận local không có trong clone sạch.


### Ảnh và biên bản browser

- [Web desktop](figures/week8_9/web-input.png) · [QR preview](figures/week8_9/web-qr-preview.png) ·
  [Brand Detector và URL X-Ray](figures/week8_9/web-brand-xray.png) ·
  [Web mobile 375 px](figures/week8_9/web-mobile.png) · [Cảnh báo Teacher](figures/week8_9/web-phishing.png).
- [Chrome native benign](figures/week8_9/extension-native-benign.png) ·
  [Chrome native phishing](figures/week8_9/extension-native-phishing.png) ·
  [Extension mất backend](figures/week8_9/extension-offline.png).

Bản thật cài unpacked với Chrome for Testing 159.0.8154.6.
Hai ca chuột phải giữ trang nguồn, gửi đúng link đã chọn và so cả nhãn, engine,
score và ngưỡng với response HTTP. Log native xác nhận hai ca này và cài/cấu hình.
Một lượt tự động desktop bị gián đoạn ở ca lỗi kế tiếp do focus cửa sổ.
Các ca còn lại chạy tự động **headless**, với link fixture gọi handler thật
của Extension, sau đó cửa sổ Extension và FastAPI thật trả kết quả. Web
headless chạy release build trên viewport 1440, 768, 375 và 320 px, kiểm
prediction, QR, inspection, mất kết nối, health degraded và retry.
HTTP 500, phản hồi lỗi schema và timeout dùng fault injection dành cho QA.
Kiểm duyệt cả request outbound cho Web và Extension không thấy yêu cầu đi
tới trang đích hoặc origin khác ngoài demo local.

[Biên bản native](tables/week8_9/chrome_native.json) ·
[Biên bản headless và SHA ảnh](tables/week8_9/browser_smoke.json)

**Nghiệm thu #38 còn chờ.** Phần Chrome, Web/Teacher, QR, X-Ray, danh mục và
benchmark đã có bằng chứng chạy. Phần Similar Cases đã có UI, contract đề xuất
và regression, chờ #36 để demo ca lịch sử thật. Review và QA độc lập thuộc #39.

## Rà soát Web ngày 25/11/2026

Bản Flutter Web giữ chủ đề navy và teal, với minh họa khiên kính WebP 53 KiB
được tải ở bố cục hai cột. Ô URL và nút quét đứng trước các công cụ bổ sung.
Dán URL điền giá trị vào form và chờ thao tác quét. Xóa URL trả focus về ô nhập
và dọn kết quả trước đó. **Chỉnh URL** giữ nguyên nội dung để sửa sau lỗi 422.
Kết quả hiển thị cảnh báo và hướng dẫn trước điểm, ngưỡng và tên mô hình.

Đã kiểm lại phản hồi hết hạn khi đổi URL, health đến muộn sau dự đoán thành công,
QR trùng URL đã nhập và trình duyệt từ chối clipboard. Desktop giữ vị trí form
khi hiện kết quả. Ở viewport hẹp, kết luận và ngưỡng tự đi vào vùng nhìn sau khi
quét. Lượt kiểm tra đo được 1440×960, 768×880, 375×720, 320×720 và 844×390
ngang với thao tác chạm giả lập trên Chromium.

- **Flutter** 58 passed, `flutter analyze` sạch, Web release build đạt. Widget
  tests bao phủ chữ 200% ở 320 px và chế độ giảm chuyển động.
- **Chromium headless** 29/29 trên commit `ae2ff835be3ed504cb97b4720e0d81d235ecb377`.
  Web và Extension dùng FastAPI và Teacher thật cho các ca bình thường. Kiểm
  clipboard mô phỏng quyền đọc của trình duyệt để giữ nguyên clipboard máy.
  API tra cứu thật vẫn trả HTTP 404. [Biên bản](tables/week8_9/web_refresh_smoke.json)
- **Hồi quy** Python 674 passed, 2 skipped, 1 deselected theo cùng phạm vi ở trên.
  Extension Node 10 passed. Đối chiếu lại Teacher 12/12 HTTP khớp, sai khác score
  tối đa bằng 0. Catalog verifier và hash artifact đã khóa đều khớp.

[Desktop](figures/week8_9/web-refresh/desktop.webp) ·
[Mobile](figures/week8_9/web-refresh/mobile.webp) ·
[Kết quả trên mobile](figures/week8_9/web-refresh/mobile-result.webp) ·
[Cảnh báo phishing](figures/week8_9/web-refresh/phishing-alert.webp)

## Đọc link từ tin nhắn và ảnh chụp ngày 25/11/2026

**Tin nhắn** tô sáng các địa chỉ web ngay trong ô nhập và liệt kê các URL để
chọn. **Đối chiếu ảnh & QR** đánh dấu vùng chữ và vị trí gần đúng của QR trên
ảnh. Thẻ so sánh đưa hai hostname lên cùng một khung trên desktop và mobile.
Người dùng có thể sửa chữ OCR và đưa URL từ mỗi nguồn về ô quét. Nội dung tin
nhắn và ảnh được xử lý trong trình duyệt. API nhận URL khi người dùng bấm quét.

OCR tiếng Việt và tiếng Anh chạy trong browser worker. Runtime và dữ liệu ngôn
ngữ khoảng 5,3 MiB, tải từ cùng origin khi đọc ảnh. Khi đọc chữ gặp lỗi, Web
giữ kết quả QR và mở ô nhập tay. Giao diện so hostname và nhắc kiểm lại dạng
Unicode/Punycode khi cách viết khác nhau. [Nguồn và hash OCR](../apps/web/web/ocr/README.md)

- Flutter analyze sạch, **65 test đạt**, release build và Wasm dry run đạt.
- **34/34 ca Chromium headless** trên commit `96640de38c3a4e5335cf84fbe7ac58cee5fabcda`.
  Ca ảnh minh họa đọc thật `example.org` từ chữ và `example.com` từ QR. Đã
  kiểm kéo thả, chọn ảnh ở 375 px, đổi URL đọc được, giữ đúng `Login?Q=A` khi
  chuyển qua Teacher/X-Ray và phạm vi request chỉ gồm hai origin local.
  [Biên bản browser](tables/week8_9/web_capture_smoke.json)
- Python **674 passed**, 2 skipped, 1 external replay deselected. Node
  Extension **10 passed**. Teacher parity **12/12 phản hồi khớp**, sai khác
  score tối đa 0. Hash sáu tệp OCR khớp trong bản build.

[Đối chiếu trên desktop](figures/week8_9/web-capture/doi-chieu-desktop.webp) ·
[Đối chiếu trên mobile](figures/week8_9/web-capture/doi-chieu-mobile.webp) ·
[Tin nhắn có link được tô sáng](figures/week8_9/web-capture/tin-nhan.webp)
