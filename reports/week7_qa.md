# QA tuần 7 — Khiêm

**Cập nhật 18/11/2026:** đã kiểm lại Web tại `5f112fc597339ea213eff3f07c745629cc18d8fc`; lỗi QR focus đã sửa, browser đạt **20/20**. Kết quả hiện hành nằm ở mục K7.5 và `qa_web_verification.json`; các mục trên `701b8f5` giữ lịch sử phát hiện lỗi. Student Python đã kiểm tại `1cad94c`; CI commit QA `3bfd45a` đạt **6/6**, còn thay đổi sau đồng bộ main chờ người dùng tạo commit. Android/device chưa nghiệm thu.

## Chốt phạm vi bàn giao Hưng và Phúc

| Phạm vi của Khiêm | Trạng thái và bằng chứng |
| --- | --- |
| K7.1 — QR Web của Hưng | Đạt trên `5f112fc`: decoder/validation/error/timeout tests, xác nhận trước predict và browser Teacher thật. 48 Flutter tests và 20 browser checks bao gồm các luồng liên quan. Timeout có kiểm soát ở unit tests; mất kết nối/restart kiểm bằng process backend thật. |
| K7.2 — Brand Detector / X-Ray của Hưng | Đạt trên cùng revision: 73 API/inspection/Teacher tests và 25 QA tests, cùng full regression. Alias/false-positive dùng lại `test_short_alias_requires_whole_token`, official-domain và reference tests trong `test_brand_features.py`; giữ nguyên reference/E2. Không suy ra đây là đánh giá accuracy trên dữ liệu mới. |
| K7.4 — phần Student Python/artifact của Phúc | Đạt trên `1cad94c`: 43 QA + 3 LightGBM + 29 Student tests cũ, chạy riêng; đủ hash/version/config/threshold/edge cases/native–JSON parity. Không còn lỗi mở trong phạm vi Python đã kiểm. |
| K7.5 — Web/API/Dart/widget regression và cấu hình CI | Các kiểm tra tại máy đạt; CI `3bfd45a` đạt 6/6. Thay đổi tương thích sau đồng bộ main chưa commit/push, nên chưa có Actions mới cho thay đổi đó. |
| Các bước liên quan Hy và nghiệm thu cuối | Chưa tiếp nhận/kiểm riêng bàn giao mới của Hy trong đợt này. Chưa chốt K7.3, Student Python–Dart parity, Android Teacher network-disabled smoke hoặc nghiệm thu toàn bộ Issue #31. |

Phần Hưng/Phúc nêu trên sẵn sàng để người dùng tự commit test, workflow và bằng chứng QA. Không cần chờ Hy để bàn giao phần đã đạt. Source hai bạn được kiểm ở checkout riêng và giữ sạch; không chép model/code sản phẩm vào repo QA. Việc approve PR Hưng và commit/push QA do người dùng thực hiện; báo cáo không tự nhận review đã được gửi chỉ từ ảnh màn hình soạn review.

## Đợt kiểm Web bàn giao ngày 17/11/2026 — lịch sử trước sửa focus

Kiểm độc lập trên Windows cho phần Hưng, trong phạm vi K7.1, K7.2 và Web/API regression của K7.5. Commit bàn giao: `701b8f5ee2b003573d991dbdee7e33c16ff2c088`, branch `feat/w7-hung-web-analysis`. Checkout mới và venv mới được dùng cho API/Teacher; source bàn giao giữ sạch sau khi chạy. Bảy source hashes trong `reports/tables/week7/verification.json` của Hưng khớp bản đã kiểm sau chuẩn hóa LF.

CPython 3.11.14 x64, dependencies theo `requirements-teacher.txt` cùng extras `api,test,teacher`; Flutter 3.47.9, Dart 3.13.7 và Chrome thật ở chế độ headless trên Windows. Teacher `teacher-stacking-v2`, SHA-256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`, threshold `0.6945740700635259`. Không train model, chấm lại external/Official Test hoặc truy cập website đích.

| Kiểm tra đã chạy | Kết quả thực tế |
| --- | --- |
| Cài dependencies vào venv mới và `pip check` | Pass, không xung đột dependencies. |
| API/inspection/Teacher upstream | 73 passed. |
| QA độc lập `tests/week7/inspection_qa.py` | 25 passed. |
| Full suite trong venv mới `api,test,teacher` | 612 passed, 3 skipped, 1 deselected; 2 warnings. |
| Research fixtures chạy riêng trong môi trường research có sẵn | 27 passed, 2 warnings; không tính là một lần full suite 639 pass. |
| Flutter analyze | No issues found. |
| Flutter tests upstream | 47 passed. |
| Release Web build, không CDN resources, API port 18767 | Pass; có cảnh báo Wasm dry-run, JavaScript release build thành công. |
| Chrome smoke thật, HTTP/Teacher thật | **19 passed, 1 failed**. |
| Repro tối giản lỗi focus trên trang mới | **1 failed**, cùng hiện tượng như full browser smoke. |
| CI của đúng commit bàn giao, đối chiếu GitHub API | 6/6 checks success; chưa bao gồm runner QA mới chưa push của Khiêm. |

Full suite thấp hơn số 639 của Hưng do venv sạch không cài extra research: module 27 test research bị collection-skip. Hai skip còn lại là bộ tham số brand regression rỗng và thiếu notebook 02/03 local handoff. Deselection duy nhất giữ theo hướng dẫn QA tuần 6: `test_real_external_bundle_matches_saved_scores`. Không chạy notebook chỉ để khớp số pass.

API QA bổ sung kiểm tra envelope của body sai kiểu/thiếu field, giới hạn URL 4096 trước trim, ký tự điều khiển/scheme không hỗ trợ, domain qua userinfo/query, Unicode–punycode, CORS, adapter trả dữ liệu lỗi, không DNS/socket/ML khi inspection và không log raw URL. Hash reference 45 brands, thứ tự E2 và source extractor khớp lock. `/inspect` không thay đổi score/label/threshold của Teacher thật trước và sau khi gọi.

Browser đã qua QR PNG/JPEG/WebP thực, preview/cancel/confirmation trước POST, ảnh hỏng/không QR/không URL/sai scheme/quá kích thước, hai nhãn Teacher thật, X-Ray/domain chính thức, URL sai port, viewport 768/375/320px, backend dừng thật rồi restart/retry cùng trang, model degraded vẫn inspect được và `/predict` trả 503. Không có page error hay request ngoài loopback. Timeout đã được kiểm trong Flutter tests có HTTP mock, không ghi đó là browser timeout thật.

## QA-W7-WEB-01 — mất focus khi sửa URL sau lỗi QR

**Mức độ: P2 khi phát hiện trên `701b8f5`; đã xác nhận sửa trên `5f112fc` ngày 18/11/2026.** Giữ mô tả và bằng chứng dưới đây để theo dõi regression.

Tái hiện tối giản trên release build, Chrome Windows:

1. Nhập `example.com` vào ô URL.
2. Chọn `apps/web/test/fixtures/broken.png`; giao diện hiển thị lỗi không đọc được ảnh.
3. Click lại ô URL, `Ctrl+A`, `Backspace`, rồi gõ hoặc paste `https://example.com/replacement`.

Mong đợi: ô giữ focus và nhận URL mới. Thực tế: sau Backspace, thông báo QR biến mất; focus DOM chuyển từ `INPUT` sang `BODY`, ô vẫn rỗng và không nhận phần gõ tiếp. Click lại ô thì nhập được. Lỗi tái hiện trên trang mới và trong full smoke; thêm thời gian chờ giữa các thao tác vẫn lỗi.

Vị trí liên quan: `apps/web/lib/main.dart::_inputChanged` xóa `_qrFailure`/`_qrCandidate`, trong khi các khối QR có điều kiện nằm trước `Form/TextFormField` trong cây giao diện. Cần giữ focus của ô nhập khi các khối phản hồi QR thay đổi; thêm regression cho thao tác bàn phím thật, vì widget test selection-only hiện tại chưa bao phủ ca này. QA chưa sửa source sản phẩm của Hưng.

Lệnh đầy đủ để cài/chạy lại Python, Flutter và browser ở [`tests/README.md`](../tests/README.md#qa-web-tuần-7--bàn-giao-của-hưng). Repro lỗi: `node tests/week7/web_smoke.cjs --handoff-root=../PhishGuardVN-w7-hung-review --scenario=qr-focus --output=reports/tables/week7/qr_focus_qa.json`.

Bằng chứng có cấu trúc: [`qa_web_verification.json`](tables/week7/qa_web_verification.json), [`web_browser_qa.json`](tables/week7/web_browser_qa.json), [`qr_focus_qa.json`](tables/week7/qr_focus_qa.json). Ảnh repro tại [`qa_qr_focus.png`](figures/week7/qa_qr_focus.png).

## Phạm vi chưa được nghiệm thu trong đợt này

Ở thời điểm kiểm `701b8f5`, chưa kiểm Android offline/device, Python–Dart Teacher parity hoặc Student/Android adapter trong đợt bàn giao Web. Chưa kết luận toàn bộ Issue #31 hoàn thành. QA không tự approve, merge, commit hoặc gửi review. Kết quả chạy lại lỗi QA-W7-WEB-01 trên commit sửa nằm ở mục K7.5 bên dưới.

## Chuẩn bị CI Web tuần 7 — lịch sử trước sửa focus

Đã bổ sung `.github/workflows/week7-web.yml`: Flutter analyze/test/release build, API/Teacher regression, QA inspection độc lập và browser smoke thật trên hai runner Ubuntu/Windows. SDK và dependency lockfile được dùng theo bản bàn giao. Source mặc định dùng SHA checkout nếu đã có Web; nếu chưa có thì dùng `WEB_HANDOFF_SHA=701b8f5...`. Có input `web_sha` để chọn commit cụ thể; không dùng đầu branch thay đổi giữa các lần chạy.

Workflow ghi SHA QA/Web, lưu log, Flutter test JSON, JUnit và JSON/ảnh browser dưới artifacts kể cả khi fail. Browser gate giữ nguyên ca lỗi focus, không tự đổi fail thành pass. Trạng thái Actions của workflow mới là **chưa chạy — chờ người dùng commit/push**; CI 6/6 ở bảng trên thuộc commit bàn giao của Hưng. Kết quả kiểm tra workflow tại máy được ghi trong `reports/tables/week7/qa_web_verification.json`.

Kiểm trước tại Windows: `actionlint 1.7.12` đạt; 10 đoạn Bash qua kiểm cú pháp; 5 trường hợp chọn SHA qua kiểm tra. `pub get --enforce-lockfile` không đổi lockfile, analyze sạch, 47 Flutter tests pass và release build thành công. Venv mới chỉ cài runtime khóa phiên bản cùng `api,test` chạy được 73 test upstream và 25 test QA, không skip. Chromium 158.0.8127.18 do Playwright cài chạy browser gate **19 pass/1 fail**, exit code 1, đúng lỗi QA-W7-WEB-01. Bằng chứng riêng: [`ci_browser_windows.json`](tables/week7/ci_browser_windows.json). Ubuntu và các thao tác của GitHub runner chưa chạy tại máy này.

Workflow này chưa bao gồm Dart package/Flutter Android hoặc Student verification; phần đó tiếp nhận theo handoff tương ứng.

## K7.4 — kiểm Student LightGBM ngày 18/11/2026

Đã tiếp nhận branch `phuc-week7-student` tại commit `1cad94c88195ebea6e4737bbfc863cbe4b2ff384` vào checkout riêng `PhishGuardVN-w7-student-review`. Source bàn giao giữ sạch sau kiểm thử; không merge hoặc chép đè backend/Web/Teacher. Venv mới dùng CPython 3.11.14 x64, runtime từ `requirements-teacher.txt`, LightGBM 4.7.0 và test dependencies. `pip check` đạt. Revision, phiên bản thư viện, SHA-256 và kết quả từng fixture có trong [`student_verification.json`](tables/week7/student_verification.json).

| Lần chạy độc lập | Kết quả thực tế |
| --- | --- |
| `tests/week7/student_qa.py` của Khiêm | **43 passed, 0 failed, 0 skipped**, 17,23 giây |
| `tests/test_student_lightgbm.py` của Phúc | **3 passed, 0 failed, 0 skipped**, 28,77 giây; 2 cảnh báo Pandas `float_precision` |
| `tests/test_student.py` và `tests/test_student_comparison.py` cũ | **29 passed, 0 failed, 0 skipped**, 4,51 giây; 3 cảnh báo Pandas cùng loại |

Đây là ba lần chạy riêng, không phải một lần full suite 75 tests. Test LightGBM upstream có fit nhỏ trên 8 URL tổng hợp để kiểm bộ export; không huấn luyện lại Teacher/Student bằng dữ liệu dự án. Không thay test/metrics cũ hoặc chấm Official Test/external.

QA bổ sung kiểm hashes của JSON/native model, features/vocabulary/IDF, reference/PSL, inference source, runtime assets và input đã đóng gói. Thứ tự 20 E2 giữ nguyên; text có 8.192 terms nên tổng đầu vào là 8.212 features. Dùng sklearn với vocabulary/IDF cố định để đối chiếu text indices/values, canonical text và E2 trong cả 52 fixture hợp lệ; cả 6 fixture lỗi bị từ chối ở từng mode. Native LightGBM, JSON batch/single và output kỳ vọng khớp label cùng score trong `atol=1e-12`.

| Mode | Model version | Threshold | Max delta native–JSON trên 52 fixture |
| --- | --- | --- | --- |
| `hard_only` | `lightgbm-student-hard_only` | `0.6157178977907972` | `6.938893903907228e-18` |
| `kd_mixed` | `lightgbm-student-kd_mixed` | `0.6204500086017339` | `1.3877787807814457e-17` |

Đã kiểm quyết định ngay dưới, bằng và trên threshold bằng score kiểm soát; cả hai mode dùng `score >= threshold`. CLI mỗi mode chạy được 5 URL từ thư mục thử và báo lỗi với input sai. Các ca sửa bytes/hash, thiếu model, sai schema/runtime/rule, đảo feature order đều bị từ chối qua luồng kiểm phù hợp. Version model bị sửa được chặn bởi hash trong loader phát hành; không coi việc gọi thẳng constructor bỏ qua manifest là luồng load chính thức.

JSON inference còn được thử trong bản sao tối thiểu không có dataset, Teacher weights hoặc file native `*.model.txt`; chặn import LightGBM, DNS/socket và `joblib.load` vẫn chạy được cả hai mode. Test riêng chặn network, Teacher loader và fit trong luồng inference. Reference/E2 và Teacher artifact vẫn giữ SHA-256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`.

CV targets đã đối chiếu hash manifest/6 file CSV nén, 13.078 Train IDs, thứ tự IDs/labels ở fitting và held của ba folds, không trùng ID/domain, score hữu hạn, record/parameters và held scores khớp OOF đã lưu. Cache model Teacher lịch sử không có trong Git; QA chỉ kiểm lineage được xuất, không tuyên bố đã load hoặc hash lại cache đó, không fit lại Teacher.

**Kết luận đợt Student:** phần artifact/config/inference Python của K7.4 đạt trên snapshot trên, chưa thấy lỗi cần yêu cầu Phúc sửa trong phạm vi đã chạy. Student vẫn `experimental`, không phải engine mặc định của ứng dụng; Teacher stacking v2 giữ vai trò chính. **Python–Dart Student parity còn chờ adapter/build của Hy**, chưa được tính là pass và chưa hoàn tất toàn bộ K7.4. Kết quả Web/CI K7.5 được cập nhật riêng ở mục bên dưới.

Lệnh cài môi trường và chạy lại cả ba bộ nằm trong [`tests/README.md`](../tests/README.md#k74--student-lightgbm-của-phúc). Chưa commit, push hoặc gửi nhận xét lên GitHub.

## K7.5 — regression và kiểm lại sửa focus ngày 18/11/2026

Đã fetch và checkout riêng đúng commit `5f112fc597339ea213eff3f07c745629cc18d8fc` của Hưng. Diff so với `701b8f5` chỉ gồm `apps/web/lib/main.dart`, regression trong `apps/web/test/week7_test.dart` và báo cáo Web. Bản sửa ổn định thứ tự semantics của card chứa form, đồng thời tránh rebuild khi không có feedback cần xóa. QA giữ nguyên browser runner đã phát hiện lỗi để kiểm lại, không thêm click lấy focus hoặc nới assertion.

| Kiểm tra trên bản sửa | Kết quả thực tế |
| --- | --- |
| Repro QR lỗi → Ctrl+A → Backspace → gõ URL mới | **1 passed**, focus và replacement text giữ đúng |
| Browser Web → FastAPI → released Teacher thật | **20 passed, 0 failed**; 0 page errors, 0 attempted external requests |
| Flutter Web | Analyze sạch; **48 passed**, không skip; release build không CDN đạt |
| API/inspection/Teacher upstream | **73 passed**, không skip |
| Inspection QA độc lập | **25 passed**, không skip |
| Teacher API acceptance tuần 6 dùng lại | **15 passed**, 17 deselected do chọn `-m teacher_api`; không skip |
| Full suite trên source Hưng | **612 passed, 3 skipped, 1 deselected**, 1 cảnh báo Pandas; 92,46 giây |
| Dart package nền | **294 passed**, không skip |
| Flutter app nền | Analyze sạch; **3 widget tests passed**, không skip |

Full suite bỏ đúng external rescore test đã quy định. Ba skip: module research thiếu extra `research`, brand regression có tập tham số rỗng, notebook 02/03 handoff chưa có. Bộ 27 research test từng chạy riêng trên `701b8f5` là lịch sử, không tính thành một lần full suite mới. Model, reference/E2 và backend không thay trong commit sửa; hashes được đối chiếu lại. Teacher vẫn stacking v2, artifact SHA-256 `63199c925b28492765019de84c178bd3f8b935a0031f6c960b5db6c31a57c4f1`, threshold `0.6945740700635259`.

Browser chạy Chromium 158.0.8127.18/Playwright 1.65.0 trên Windows với CPython 3.11.14, Flutter 3.47.9/Dart 3.13.7. Bao phủ QR thật PNG/JPEG/WebP, hủy/xác nhận, ảnh lỗi/non-URL/oversized, hai nhãn Teacher, rule/ML separation, invalid port, viewport 768/375/320px, dừng backend thật rồi restart/retry, degraded model. Bằng chứng mới: [`qr_focus_fixed.json`](tables/week7/qr_focus_fixed.json), [`web_browser_fixed.json`](tables/week7/web_browser_fixed.json); ảnh cuối nằm cùng tên `.png`. Bằng chứng fail cũ được giữ riêng, không ghi đè thành pass.

`dart test` gồm các fixture golden có sẵn của extractor và Teacher pipeline; app widget tests kiểm app nền và assets đã đồng bộ theo README. Đây là kiểm trên desktop runner, không chứng minh đã chạy Teacher trên Android tắt mạng hoặc đã nhận đầy đủ build Android tuần 7 của Hy.

Workflow `.github/workflows/week7-web.yml` hiện tên **Week 7 QA**: hai job Web Ubuntu/Windows và hai job Student Python Ubuntu/Windows. Source Web ghim `5f112fc`, Student ghim `1cad94c`; mỗi nguồn checkout riêng. Có analyze/test/build Web, API/full regression, gate Teacher tuần 6, Dart test và app widget tests, real-browser smoke, 43 + 3 + 29 tests Student. Upload versions/SHA/logs/JSON/JUnit/ảnh kể cả khi fail; gate trọng tâm không nhận thiếu test hoặc skip. Full regression cần extras `api,test,teacher`; thử cấu hình chỉ `api,test` đã bộc lộ thiếu LightGBM, nên CI đã sửa dependency, không bỏ test để né lỗi.

Workflow đã qua actionlint và kiểm cú pháp/logic chọn SHA tại máy. Khi chuẩn bị đợt kiểm này, workflow QA chưa commit/push; sau đó người dùng đã phát hành `3bfd45a` và 6/6 checks đạt (xem cập nhật đồng bộ main bên dưới). Sáu checks upstream Hưng được xác minh riêng, không dùng thay cho CI QA. Có source checkout sạch sau cập nhật và venv riêng được dùng lại; không gọi lần fetch này là clean clone/venv mới hoàn toàn tại `5f112fc`.

**Kết luận:** QA-W7-WEB-01 đã khắc phục; trong phạm vi Web đã chạy không còn lỗi mở cần Hưng sửa. Có thể gửi review approve cho commit này dựa trên các kết quả trên. **K7.5 chưa hoàn tất toàn bộ**: cần chạy Actions sau khi người dùng tự commit/push, nhận build/adapter tương ứng để chạy Android network-disabled Teacher smoke và hoàn thiện báo cáo nghiệm thu cuối. Không tick Android/device bằng kết quả Dart/widget hoặc browser responsive. QA chưa commit, push, gửi review hoặc merge.

## Đồng bộ main vào checkout QA — kiểm tại máy ngày 18/11/2026

Người dùng đã commit/push QA tại `3bfd45ac2b5c78b0b251584478c607cfe31018a3`; đã xác minh **6/6 checks success** của đúng commit này. Sau đó lấy `origin/main=19eaaa3f3ddbd4d6e1ffaef01a6c31ce89b02fcf` vào nhánh `test/week7-web-student-qa` bằng merge **dừng trước commit**. Không có conflict; chưa tạo merge commit hoặc push, không thay đổi nhánh `main`. Trước commit kết thúc, `HEAD` vẫn là `3bfd45a` nên Git vẫn báo **behind 18/ahead 1**, mặc dù cây file và index đã chứa các thay đổi main.

Đã kiểm trực tiếp cây file đang ghép này, không dùng kết quả checkout Hưng để thay cho QA:

| Kiểm tra trong checkout QA | Kết quả |
| --- | --- |
| Python 3.11.14, đủ extras và research | `pip check` đạt; **624 passed, 2 skipped, 1 deselected**, 3 cảnh báo upstream |
| Backend chạy thật với Python 3.11 | Health `model_ready=true`, predict hợp lệ HTTP 200, port sai HTTP 422 `invalid_port` |
| Web lấy từ main | Analyze sạch; **28 tests passed** |
| Dart package lấy từ main | **294 tests passed**; analyzer còn 1 warning và 8 info có sẵn trong source, không có error |
| Flutter app nền lấy từ main | Analyze sạch; **3 widget tests passed** |

Lần chạy Dart đầu phát hiện reference CSV đã có CRLF ở máy làm sai raw-byte SHA-256 (`247c6b5d...`). Đã xác nhận khác biệt chỉ ở xuống dòng và khôi phục nguyên bytes LF từ Git `origin/main`; SHA trở lại đúng `6d434533...`, sau đó 294 tests đạt. Không chỉnh nội dung reference, không sửa hash kỳ vọng hoặc nới test. Các assets chạy app được đồng bộ vào thư mục ignored theo README.

`.venv` cũ tại QA là Python 3.13.7, không được dùng để nhận nghiệm thu Teacher đóng băng. Lần kiểm trên dùng môi trường QA CPython 3.11 đã có và được xác nhận dependencies. Cấu hình VS Code cục bộ `.vscode/settings.json` trỏ interpreter 3.11/Flutter SDK; file này được ignore, không gửi lên repo. Cần chọn lại interpreter hoặc restart analysis server nếu VS Code giữ lựa chọn/cache cũ; không tuyên bố bảng Problems đã trống khi chưa xem lại UI.

Web/app nền từ main chưa chứa QR/inspect tuần 7 hoặc Teacher UI mới của Hy. Vì vậy workflow QA đã sửa điều kiện chọn source: chỉ dùng checkout QA làm Web tuần 7 khi có đủ `week7_test.dart` và `url_inspection.py`; nếu không, tiếp tục dùng pin đã kiểm `5f112fc`. Actionlint và 10 ca chọn SHA đã qua, trong đó có ca main chỉ chứa Web tuần 6. Thay đổi guard này chưa có Actions mới đến khi người dùng tự commit/push.

Bằng chứng: [`main_sync_verification.json`](tables/week7/main_sync_verification.json). Các warning/info Dart thuộc source package hiện có ở main, không phải conflict do merge; chưa chỉnh code người phụ trách package để làm sạch lint. Bản Hy `a4d7b0e` đã lấy riêng và chạy được 46 Flutter/294 Dart tests; phần kiểm độc lập và Android device tiếp tục riêng sau khi chốt đồng bộ. Android SDK/thiết bị chưa được tìm thấy tại máy QA, không nhận device/offline smoke là pass từ test host.
