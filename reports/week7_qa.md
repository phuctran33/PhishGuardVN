# QA tuần 7 — Khiêm

**Cập nhật 22/11/2026 — kiểm lại HEAD Hy `680a8bd`:** bộ QA giữ nguyên đạt **79/79** trên host và Android emulator; khớp **54 URL hợp lệ + 9 rejected**, max score delta `5.551115123125783e-17`. Bản tích hợp sạch từ main `4d13bee` + diff PR #33 đã sync assets từ repo **không cần ref PR #35**, từ chối model sai SHA-256, analyze sạch, **54 Flutter tests + 294 Dart tests** đạt và build APK release thành công. Ba lần mở lại APK release khi tắt mạng đạt, đã khôi phục mạng. Teacher vẫn mặc định; Student experimental. Xem [bằng chứng HEAD mới](tables/week7/hy_head_recheck.json).

CI QA **14/14 tại `18e076e` đã đạt**; PR #33 **6/6 tại `680a8bd` đã đạt**. Đây là kết quả của hai revision đã xác minh, không thay cho CI của thay đổi pin/report chưa commit hiện tại. Sau khi người dùng push, cần kiểm Actions trên đúng commit QA mới. Các mục 18–20/11 bên dưới là lịch sử của từng lượt kiểm, không phải blocker hiện tại.

**Lịch sử 20/11/2026 — đã kiểm bản sửa MLP của Hy tại `f817ec9`:** Python–Dart và Python–Android emulator khớp **54/54 URL hợp lệ + 9/9 rejected**, max score delta **`5.551115123125783e-17`** (giới hạn `2e-6`). Bộ QA giữ nguyên đạt **79 passed, 0 failed, 0 skipped** trên cả host và Android; QA-W7-MLP-01 đã sửa và xác minh. Loader/version/hash/threshold, APK release, ba lần mở lại app khi tắt mạng và suy luận Student thật đã kiểm. Phạm vi kiểm tại máy đã đạt; còn người dùng commit/push, xác nhận Actions cho commit mới và sign-off Issue #31. Xem [kết quả implementation MLP](#k74--implementation-mlp-của-hy-ngày-20112026).

**Lịch sử 19/11/2026 — nhận bundle/Python:** đã nhận PR #35, commit `bc3a3a7`, model **`student-mlp-kd-int8-v1`**. Phần bundle/Python đạt 86 QA độc lập và 55 stacking/MLP fixtures; đủ 54 URL hợp lệ/9 ca từ chối, score delta lớn nhất `2.7755575615628914e-17`. Đây là phiên bản mới, không lấy kết quả Android LightGBM thay cho MLP. Lượt 19/11 chỉ xác minh bundle/Python; phần Dart/Android/offline đã được bổ sung trong lượt 20/11 ở dưới. Teacher/Web đã kiểm trước đó vẫn giữ nguyên. Xem [lượt kiểm MLP mới](#k74--student-mlp-int8-bàn-giao-ngày-19112026).

**Cập nhật 18/11/2026:** Web `5f112fc` đạt **20/20** browser checks trên Windows; Student `1cad94c` đã kiểm Python, Dart và Android emulator. Teacher của Hy tại `94abdbf` đã kiểm riêng trên **Android 17/API37/x86_64**: parity 47 classified/9 rejected, loader/UI errors và APK release nguyên bản offline đạt. Xem mục [Teacher Android runtime](#k73--teacher-android-runtime-và-release-offline). Chưa kiểm điện thoại vật lý. CI tại `8943bbe` có một lỗi browser Ubuntu ở lượt PR; phạm vi browser đã thu về Windows, thay đổi mới còn chờ người dùng commit/push rồi kiểm Actions. Không nhận toàn bộ Issue #31 hoàn tất trước bước đó và xác nhận nghiệm thu cuối.

## Chốt phạm vi bàn giao Hưng và Phúc

| Phạm vi của Khiêm | Trạng thái và bằng chứng |
| --- | --- |
| K7.1 — QR Web của Hưng | Đạt trên `5f112fc`: decoder/validation/error/timeout tests, xác nhận trước predict và browser Teacher thật. 48 Flutter tests và 20 browser checks bao gồm các luồng liên quan. Timeout có kiểm soát ở unit tests; mất kết nối/restart kiểm bằng process backend thật. |
| K7.2 — Brand Detector / X-Ray của Hưng | Đạt trên cùng revision: 73 API/inspection/Teacher tests và 25 QA tests, cùng full regression. Alias/false-positive dùng lại `test_short_alias_requires_whole_token`, official-domain và reference tests trong `test_brand_features.py`; giữ nguyên reference/E2. Không suy ra đây là đánh giá accuracy trên dữ liệu mới. |
| K7.4 — LightGBM của Phúc (lịch sử) | Đạt trên `1cad94c`: 43 QA + 3 LightGBM + 29 Student tests cũ, chạy riêng; đủ hash/version/config/threshold/edge cases/native–JSON parity. Giữ kết quả đúng phiên bản cũ, không thay cho MLP mới. |
| K7.4 — MLP int8 của Phúc và implementation Hy | Bundle `bc3a3a7`; kiểm lại Hy `680a8bd` đạt 79/79 trên host và Android, parity 54/9 đạt. Python QA 86 thuộc lượt bundle đã xác minh trước đó. QA-W7-MLP-01 không tái hiện; release/offline/cold start đạt. Xem `hy_head_recheck.json`; không đổi lịch sử tại `f817ec9`. |
| K7.3 — Teacher Android của Hy | Đạt trong phạm vi emulator tại `94abdbf`: 47/9 parity khớp Python, metadata/assets, missing/corrupt model/sai threshold, UI hai nhãn thật/port lỗi/retry. APK release nguyên bản đóng/mở 3 lần khi offline và phân loại URL mẫu đạt. Không sửa mã sản phẩm Hy. |
| K7.5 — Web/API/Dart/widget regression và cấu hình CI | Web E2E Windows, regression và Android offline đã có bằng chứng. QA `18e076e` đạt 14/14 CI; host jobs giữ Ubuntu/Windows, browser chỉ nghiệm thu Windows. Lượt pin Hy `680a8bd` đạt local; CI của thay đổi pin mới còn chờ người dùng push. |
| Nghiệm thu cuối | K7.1/K7.2, K7.3 emulator và K7.4 MLP có bằng chứng trong phạm vi đã kiểm. Còn Actions của thay đổi QA mới sau người dùng commit/push và sign-off Issue #31. Điện thoại vật lý nằm ngoài phạm vi emulator đã thống nhất. |

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

**Kết luận đợt Python ban đầu:** phần artifact/config/inference Python của K7.4 đạt trên snapshot trên, chưa thấy lỗi cần yêu cầu Phúc sửa trong phạm vi đã chạy. Student vẫn `experimental`, không phải engine mặc định của ứng dụng; Teacher stacking v2 giữ vai trò chính. Lúc kiểm Python chưa có Student Dart adapter; kết quả triển khai theo hướng dẫn Hy `94abdbf` được cập nhật ở mục cuối báo cáo, không dùng số Python này thay cho Dart/Android.

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

Workflow `.github/workflows/week7-web.yml` hiện tên **Week 7 QA**: hai job Web Ubuntu/Windows và hai job Student Python Ubuntu/Windows. Source Web ghim `5f112fc`, Student ghim `1cad94c`; mỗi nguồn checkout riêng. Có analyze/test/build Web, API/full regression, gate Teacher tuần 6, Dart test và app widget tests, real-browser smoke trên Windows, 43 + 3 + 29 tests Student. Upload versions/SHA/logs/JSON/JUnit/ảnh kể cả khi fail; gate trọng tâm không nhận thiếu test hoặc skip. Full regression cần extras `api,test,teacher`; thử cấu hình chỉ `api,test` đã bộc lộ thiếu LightGBM, nên CI đã sửa dependency, không bỏ test để né lỗi.

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

## K7.3 — Teacher Android của Hy, kiểm trên host

Đã kiểm riêng bàn giao `a4d7b0e8e7d7845368bb3061c8e754c7cbe1224e`, branch `feat/w7-android-teacher-integration`. Source Hy giữ sạch; chỉ sinh assets và file QA dưới các thư mục ignored. Không sửa implementation, Teacher bundle/lock, công thức E2/reference hoặc Student.

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Flutter app Hy | Analyze sạch; **46 tests passed**, không fail/skip |
| Dart package Hy | **294 tests passed**, không fail/skip |
| QA độc lập bổ sung | Analyzer sạch; **5 tests passed**, không fail/skip |
| Python mới → classifier thật của app Dart | **47/47 input hợp lệ, 9/9 input lỗi khớp**, không mismatch |
| Sai số score Python–Dart | Max delta **`8.881784197001252e-16`**, tolerance **`1e-6`** |
| Android runtime/emulator/device, cold start khi tắt mạng | **Chưa chạy** — người dùng xác nhận chưa có SDK/emulator/thiết bị |

QA tạo output mới bằng `load_teacher(root)` chính thức, với DNS/socket bị chặn. Bộ input gồm 41 ca shared fixture có sẵn và 15 probe bổ sung cho scheme/case, scheme-relative, userinfo/port/fragment, IDNA/Unicode path, IPv6, dấu cách bên trong, port/host lỗi, rỗng, khoảng trắng hai đầu và ký tự điều khiển. Mỗi ca lưu score/class/status hoặc lý do từ chối. Không fit, không dùng dataset/Official Test/external, không chọn lại threshold.

Test Flutter độc lập nạp model thật qua loader app và đối chiếu với output Python mới. Đã kiểm model version, threshold, rule, member order và feature order theo manifest/lock, hashes/kích thước export và reference. Teacher vẫn `teacher-stacking-v2`, threshold `0.6945740700635259`, quy tắc `score >= threshold`; score chưa hiệu chuẩn. Các ca lỗi nạp model có trong 46 tests upstream (missing/corrupt/JSON/schema/hash/contract/init); QA bổ sung kiểm thiếu asset và sửa threshold phải báo lỗi, không fallback prediction. Trên host, chặn tạo HTTP client vẫn nạp model và phân loại được. Việc này không chứng minh Android OS đã tắt mạng.

Nguồn test của Khiêm là `tests/week7/android_teacher_qa_test.dart.in`. Helper `android_reference.py` chép nguyên bytes nguồn vào `mobile/app/.dart_tool/week7_teacher_qa_test.dart` của checkout Hy, rồi Flutter compile/analyze/test trong đúng package. Cách này tránh hàng loạt import diagnostics do đặt test Dart độc lập ngoài ngữ cảnh Flutter, không tắt lint hoặc bỏ assertion. Test được sinh đã qua analyzer không issue và thực thi đủ 5 ca.

Bằng chứng: [`android_verification.json`](tables/week7/android_verification.json), [`android_python_reference.json`](tables/week7/android_python_reference.json), [`android_host_parity.json`](tables/week7/android_host_parity.json). Môi trường: Windows x64, CPython 3.11.14 với frozen requirements, Flutter 3.47.9/Dart 3.13.7. Các lệnh tái lập nằm ở [`tests/README.md`](../tests/README.md#k73--kiểm-teacher-android-của-hy). Bản Hy có báo cáo emulator riêng; QA chưa chạy lại trên emulator nên giữ đó là bằng chứng do Hy cung cấp, không gán thành kết quả tự chạy của Khiêm.

CI đã thêm checkout Hy riêng, ghim revision trên; đồng bộ bảy app assets, chạy 294/46/5 tests và parity trên Ubuntu/Windows host. Vẫn có bốn job trong workflow: hai Web/Android host, hai Student. Actionlint, cú pháp và gate báo cáo được kiểm tại máy; thay đổi này **chưa có Actions thực** trước khi người dùng tự commit/push. Không tự thêm job giả Android device hoặc nhận host job là offline smoke Android.

**Kết luận lượt host ban đầu:** parity/metadata/assets/loading-errors trên host đạt; tại thời điểm đó chưa kiểm Android runtime. Kết quả bổ sung trên emulator ở mục [Teacher Android runtime](#k73--teacher-android-runtime-và-release-offline), không suy ra từ Student. Chưa commit, push, approve hoặc merge thay người dùng.

## K7.4 — Student Dart theo hướng dẫn Hy `94abdbf`

Đã lấy và đọc commit `94abdbf9d9fd1be6452284d2a84f26ec937f2474` tại checkout Hy riêng. Commit chỉ bổ sung `docs/week7_student_android_handover.md`; không có Student Dart implementation. Đã triển khai adapter inference **trong `tests/week7/student_android`**, tách khỏi source/app Teacher của Hy. Không đổi engine mặc định, Student artifacts, threshold, Teacher/E2/reference hoặc thực hiện training. Package extractor/canonicalization tái sử dụng từ main; toàn bộ Dart library khớp source Hy khi chuẩn hóa LF.

| Kiểm tra đã chạy trên Windows laptop | Kết quả |
| --- | --- |
| Reference Python mới, model Phúc `1cad94c` | Hai mode KD/hard-only; 52 hợp lệ + 6 reject có sẵn, thêm 3 hợp lệ + 3 reject QA; khớp frozen outputs |
| Adapter/vectorization/tree/loader/error tests | **44 passed, 0 failed, 0 skipped**; analyzer sạch |
| Parity KD Python–Dart | **55/55 classified + 9/9 rejected**; max score delta **`1.1102230246251565e-16`** |
| Parity hard-only Python–Dart | **55/55 classified + 9/9 rejected**; max score delta **`5.551115123125783e-17`** |
| Intermediate features cả hai mode | Canonical text/indices khớp; max TF-IDF delta **`5.551115123125783e-17`**, E2 delta **`3.9968028886505635e-15`** |
| App QA sinh ra, assets/UI host tests | **2 passed**, không fail/skip; analyzer sạch, gồm source test/driver Android |
| Android emulator runtime/profile | **3 test ứng dụng passed**, thêm 1 teardown framework; mỗi mode 55 classified + 9 rejected; loader/UI đạt |
| Android OS offline | Airplane mode bật, Wi-Fi/data tắt, routes rỗng; force-stop rồi chạy lại native parity và prediction đạt |
| Release APK / cold start / RAM | APK x86_64 18.498.267 bytes; 3 lượt cold start tới model readiness đạt; PSS sau native prediction 87.208 KB |

Runtime: CPython 3.11.14, Flutter 3.47.9/Dart 3.13.7, Windows x64. Score tolerance `1e-6`; TF-IDF `1e-12`, E2 `1e-6`. So cả vector ghép 8.192 TF-IDF + 20 E2, prediction label/class/version/threshold/rule và trạng thái uncalibrated/experimental. Character n-gram dùng Unicode code points; có probe ký tự ngoài BMP. KD threshold giữ `0.6204500086017339`, hard-only `0.6157178977907972`; không nhân learning rate lần nữa. Các test synthetic kiểm decision boundary bằng/nhỏ/lớn hơn threshold; URL KD gần ngưỡng nhất trong bộ này cách `0.018804223172239287`, không nhận là coverage URL sát ngưỡng `1e-6`.

Loader kiểm manifest/model/features/reference/PSL bằng trusted hash và byte size. Đã thử thiếu file, hash sai cùng kích thước, size sai, JSON lỗi, selected mode/threshold sai, schema/feature order/IDF lỗi, sai tree count/index/child/cycle/value và model initialization. Lỗi input/load không trở thành benign. Python load/predict được chặn DNS/connect/connect_ex; Dart host load/predict chạy với HTTP client bị chặn. Đây không phải bằng chứng OS Android đã mất mạng.

App QA `.android_harness` được sinh vào thư mục ignored, có ID riêng và thông báo Student thử nghiệm; Teacher app của Hy giữ nguyên. Sau khi người dùng cài Android Studio/SDK, đã mở **Medium Phone API 37, Android 17, x86_64**, cài thêm NDK 28.2.13676358/API 36 theo compile config. Đã build/cài profile và release APK thật. Mỗi mode khớp Python 55 classified/9 rejected, không mismatch; max score delta bằng kết quả host. Profile offline KD có 550 mẫu sau 5 warm-up: p50 **1,018 ms**, p95 **1,761 ms**, mean **1,101 ms**, loader đầu **134,202 ms**. Không lấy timing Dart VM Windows thay cho các số đo này.

Release app từ launcher được force-stop/mở lại 3 lần khi Android OS tắt mạng: loader **822–1.065 ms**, activity TotalTime **1.559–1.680 ms**, launch-to-ready quan sát tại host **1.800–2.174 ms**. Chỉ số cuối gồm overhead ADB/polling, là process cold start với filesystem/shader cache giữ lại, không phải timing Android thuần. Native ADB touch cho `example.com` trả benign, score `0.05418895367061694`; PSS sau prediction **87.208 KB**. APK release QA x86_64 **18.498.267 bytes**, SHA-256 `e43640d38a45c589e08d494ea4404f904480ffff50e138439fee13424f78bf4e`. APK QA chứa cả hard-only/fixtures nên không phải kích thước production KD tối thiểu. Chưa xác minh điện thoại thật hoặc tích hợp Student vào UI sản phẩm của Hy.

Lượt UI integration đầu bộc lộ stale editing value do dùng `TestTextInput` trong khi native IME còn hoạt động; một lượt chẩn đoán còn chọn cả EditableText bên trong SelectableText. Đã giới hạn finder vào ô URL và đăng ký keyboard transport của Flutter test theo cảnh báo trong SDK, giữ nguyên assertion nhãn. Lượt chạy lại offline đạt cả benign/phishing/invalid port, loader errors và parity. Đây là kiểm UI với keyboard transport được kiểm soát, không nhận native/physical IME đã kiểm. Lượt release offline riêng dùng native touch và URL mặc định, không dùng keyboard stub. Mạng emulator được khôi phục sau từng lượt. Lỗi cấu hình template built-in Kotlin đã sửa trong helper QA; SDK/NDK cài đủ, không chỉnh project Hy hoặc artifacts để né lỗi.

CI Student Ubuntu/Windows được mở rộng để tạo reference, chạy 44 tests/parity và 2 tests app QA trên host; gate không nhận skip/thiếu test. Actionlint và kiểm cú pháp/chọn SHA đã chạy tại máy, **chưa có Actions cho thay đổi mới**. Lệnh tái lập và các bước Android ở [`tests/README.md`](../tests/README.md#student-android--triển-khai-qa-theo-hướng-dẫn-hy-94abdbf). Bằng chứng: [`student_android_verification.json`](tables/week7/student_android_verification.json), [`student_android_python_reference.json`](tables/week7/student_android_python_reference.json), [`student_dart_parity.json`](tables/week7/student_dart_parity.json).

**Kết luận:** Student QA đạt Python–Dart trên host và Android emulator, có offline smoke, loader errors, release APK và số đo performance kèm giới hạn. Chưa phát hiện lỗi model/inference cần yêu cầu Phúc/Hy sửa trong phạm vi Student đã chạy. Kết quả QA không đổi manifest/model (`android_verified=false`, `student_default=false` vẫn giữ nguyên), không promote Student. Teacher Android K7.3 có lượt nghiệm thu riêng ở bên dưới; chưa kiểm điện thoại thật. Chưa commit, push, approve hoặc merge.

## Phạm vi browser CI sau lượt chạy `8943bbe`

Issue #31 yêu cầu CI phù hợp và Web E2E thật, không quy định phải chạy browser trên cả Windows và Ubuntu. Theo phạm vi người phụ trách chọn, workflow giữ browser smoke trên Windows; Ubuntu tiếp tục chạy API/Teacher/Dart/Flutter regression trên host và Student QA. Bốn bước Node.js/npm/Chromium/browser có điều kiện `runner.os == 'Windows'`; giữ nguyên 20 ca trong `web_smoke.cjs`, không thêm retry, bỏ assertion hoặc đổi lỗi thành pass.

Đã đối chiếu cùng head `8943bbe2b3ac18cb304f3505bed1c478c2b0040f`: [lượt push #3](https://github.com/phuctran33/PhishGuardVN/actions/runs/44275253747) đạt cả bốn job; [lượt PR #4](https://github.com/phuctran33/PhishGuardVN/actions/runs/44276030588) đạt ba job, riêng browser Ubuntu có 19 passed/1 failed ở thao tác thay URL sau lỗi QR. Chưa đủ bằng chứng quy lỗi cho hệ điều hành hoặc mã sản phẩm của Hưng; lỗi browser Ubuntu còn chưa được xử lý và nằm ngoài phạm vi nghiệm thu browser hiện tại.

Chạy lại toàn bộ browser smoke bằng Chromium của Playwright trên Windows, source Hưng `5f112fc`: **20 passed, 0 failed**, không page errors hoặc yêu cầu ra ngoài loopback; ca thay URL sau lỗi QR đạt. `actionlint` đạt cho cấu hình mới. Lệnh tự kiểm nằm trong [`tests/README.md`](../tests/README.md). Cấu hình giới hạn browser này còn phải được người dùng commit/push và kiểm kết quả Actions trên head mới; không dùng kết quả cũ để nhận CI mới đã pass.

## K7.3 — Teacher Android runtime và release offline

Ngày 18/11 đã chạy riêng app Teacher của Hy tại `94abdbf9d9fd1be6452284d2a84f26ec937f2474` trên Medium Phone emulator **Android 17/API 37/x86_64**. Flutter 3.47.9/Dart 3.13.7, CPython 3.11.14; source Teacher app bằng bản `a4d7b0e`, commit mới chỉ thêm tài liệu. Build release nguyên bản đạt, không cần sửa Gradle hoặc mã sản phẩm Hy.

| Kiểm tra thực tế | Kết quả |
| --- | --- |
| Python mới và Flutter host | 47 classified/9 rejected, 5 QA tests đạt trên `94abdbf` |
| Teacher Python → Android profile | **47/47 classified, 9/9 rejected**, score delta lớn nhất `8.881784197001252e-16`, atol `1e-6` |
| Hợp đồng/assets trên runtime | Teacher version, threshold `0.6945740700635259`, rule, 20-feature order và SHA-256 manifest/model khớp |
| Loader và UI lỗi | Missing model, model hỏng giữ nguyên kích thước, sai threshold đều bị chặn; boot error không có prediction, retry nạp được model thật |
| UI Android integration | Hai nhãn thật benign/phishing và port lỗi đạt; **3 nhóm kiểm ứng dụng**, không cộng ca setup/teardown framework |
| Mạng Android | Airplane on, Wi-Fi/data off, không default route IPv4/IPv6; HTTP guard riêng trong lượt parity; mạng được khôi phục đúng `0/1/1` sau mỗi lượt |
| APK release nguyên bản | 19.130.745 bytes, SHA-256 `86b27917e9ad06b1a31ba6726b55d84484242a17da9ffaa733ac78187692c08a` |
| Release offline smoke | Force-stop/mở lại **3 lần**, mỗi lần vào được app; native ADB touch URL mẫu trả benign, score hiển thị `0.455156`, model/rule/threshold đúng |

Bản integration là bản chép mã `lib/` và Android build của Hy nguyên bytes vào thư mục ignored của QA, kèm provenance/hashes. Chỉ bổ sung reference Python, SDK `integration_test` và entrypoint test; không mock prediction. Lượt release sau đó cài lại APK được build trực tiếp từ checkout Hy, không dùng integration entrypoint. UI integration dùng keyboard transport của Flutter test; release smoke dùng native ADB touch trên URL mẫu. Không nhận là đã kiểm mọi native IME hoặc điện thoại vật lý/ARM64.

Ba process cold-start có Android Activity TotalTime 1.214/1.485/1.435 ms; thời gian host quan sát tới UI 3.726/4.355/4.040 ms gồm ADB/UIAutomator polling. Các lần mở lại giữ filesystem/shader cache; không coi đây là benchmark thiết bị production. Lượt điều khiển QA đầu tiên đọc mỗi thuộc tính `text` nên không tìm được Chip URL có `content-desc`; đã sửa bộ đọc accessibility, không sửa app, rồi kiểm lại thành công. Controller cũng chờ trạng thái Wi-Fi ổn định trước khi xác nhận phục hồi mạng.

Bằng chứng: [`teacher_android_runtime.json`](tables/week7/teacher_android_runtime.json), [`teacher_android_runtime_results.json`](tables/week7/teacher_android_runtime_results.json), [`teacher_android_release.json`](tables/week7/teacher_android_release.json), [ảnh release offline](figures/week7/teacher_android_release_offline.png), tổng hợp [`android_verification.json`](tables/week7/android_verification.json). Lệnh build/chạy lại và dependencies ở [`tests/README.md`](../tests/README.md#teacher-android-runtime-và-apk-release).

**Kết luận:** K7.3 và smoke Teacher Android offline của K7.5 đạt trong phạm vi emulator đã chạy; chưa phát hiện lỗi trong app Teacher cần yêu cầu Hy sửa ở các ca này. Không sửa models/locks/reference, không thay Teacher bằng Student, không train hoặc chấm Official Test/external. Còn kiểm Actions trên commit QA mới và bàn giao/sign-off cuối; mọi commit/push/review do người dùng thực hiện.

## K7.4 — Student MLP int8 bàn giao ngày 19/11/2026

Tiếp nhận PR [#35](https://github.com/phuctran33/PhishGuardVN/pull/35), revision **`bc3a3a7054e2f6e6e733595f40f38439784536a1`**, branch `phuc-week7-student`, trong checkout riêng. Đọc contract `docs/week7_android_mlp_handoff.md`, manifest, script loader và Python reference; không merge Student vào nhánh QA hoặc thay model Teacher. Handoff MLP mới không phải bộ LightGBM đã nghiệm thu ngày 18/11.

| Kiểm tra tại Windows/CPython 3.11.14 | Kết quả thực tế |
| --- | --- |
| Dependency và `pip check` | Đạt trong venv MLP riêng; dùng requirements Teacher đã khóa, test extras. LightGBM 4.7.0 chỉ bổ sung cho stacking fixtures cũ |
| QA độc lập `student_mlp_qa.py` | **86 passed, 0 failed, 0 skipped**; cũng đạt 86 trong môi trường LightGBM giống job CI, không cộng hai lần thành 172 |
| Test MLP upstream | **2 passed**; nằm trong lượt regression 55 bên dưới |
| Regression stacking + MLP | **55 passed**, gồm 53 stacking + 2 MLP; không training project data |
| Shared fixtures | **54 classified, 9 rejected**, labels/version/threshold/rule khớp; max score delta **`2.7755575615628914e-17`**, tolerance **`2e-6`** |
| Đường tính signed int8 độc lập | Giải mã byte có dấu, layout `4096 × 64`, scale theo từng nút ẩn, ReLU rồi sigmoid; đối chiếu scalar trên 54 URL, max delta **`2.7755575615628914e-17`** |
| Metadata/assets | SHA-256 bốn file bàn giao và PSL, threshold `0.72961075`, class mapping, score uncalibrated và Teacher provenance khớp lock |
| Edge cases và lỗi load | Unicode/IDNA/code point, IPv6, case/percent escape, zero TF-IDF, synthetic threshold boundary; missing/corrupt model/manifest, sai version/threshold/score kind và PSL đều bị chặn |
| Portable offline Python | Chạy trong thư mục thử chỉ có code runtime/model/manifest/PSL, không Teacher bundle/dataset; chặn DNS/socket, Teacher loader và training; inference vẫn đạt |
| Android/Dart MLP | **Chưa chạy — chưa có adapter/build MLP của Hy trong nguồn đã bàn giao** |

Model gzip **283.334 bytes**, SHA-256 **`8d118ac5346543bdfa29b7970b48ae206305d5fe8992e0c4754aa070cc032341`**; PSL **75.007 bytes**, SHA-256 **`fb8419c17a533dfdd57199da1cef1481974119fe23ce7c478af3d12eb8466c8f`**. Model+PSL **358.341 bytes** không phải kích thước APK hoặc RAM trên Android. `android_verified=false` trong manifest giữ nguyên; QA không sửa artifact hoặc tự promote Student.

Lượt stacking đầu tiên thiếu LightGBM trong venv chỉ cài test extras; bổ sung đúng dependency 4.7.0 rồi chạy lại 55/55 đạt. Lượt portable QA đầu dùng nhầm tên module Teacher trong phép chặn; đã sửa bộ test sang `phishguard_vn.teacher` và kiểm lại 86/86. Đây là lỗi môi trường/bộ QA đã xử lý, không phải lỗi model bàn giao. Chưa phát hiện lỗi cần yêu cầu Phúc sửa trong phạm vi bundle/Python đã chạy.

CI thêm checkout MLP ghim riêng và hai bước pytest trong job Student Ubuntu/Windows hiện có, lưu XML/JSON/manifest/SHA dưới artifacts. Gate không nhận thiếu case, skip hoặc sai tolerance; giữ toàn bộ regression LightGBM và bốn job cũ. Số job không tăng. Actionlint/cú pháp/gates được kiểm tại máy; **Actions cho thay đổi này còn chờ người dùng commit/push**. Kết quả 14/14 ở `68e7a6b` thuộc đợt trước, không dùng làm bằng chứng CI cho MLP mới.

**Trạng thái tại lượt 19/11:** nguồn Hy khi đó ở `94abdbf`, chưa có MLP adapter. Ngày 20/11 đã nhận `feb5763` và kiểm implementation thật như mục dưới; trạng thái chờ adapter trước đây đã được thay thế. Kết quả Teacher 47/9 và LightGBM 55/9 vẫn là bằng chứng riêng cho các phiên bản đó.

Bằng chứng: [`student_mlp_verification.json`](tables/week7/student_mlp_verification.json), [`student_mlp_python.json`](tables/week7/student_mlp_python.json). Lệnh cài/chạy lại ở [`tests/README.md`](../tests/README.md#k74--student-mlp-int8-bàn-giao-ngày-1911). Các số nghiên cứu/đối chiếu Train 13.078 URL do Phúc cung cấp vẫn là bằng chứng upstream; QA không train hoặc chạy lại đánh giá đó, không dùng Official Test/external.

## K7.4 — implementation MLP của Hy ngày 20/11/2026

Kiểm PR #33 tại **`f817ec96eee8f5301c06bae6c59b0059b9fe3d78`**, đối chiếu gói Phúc **`bc3a3a7054e2f6e6e733595f40f38439784536a1`**. Bản QA sao chép 36 file source/Android config/lock nguyên bytes từ Hy vào thư mục được Git ignore, chỉ thêm entrypoint kiểm thử và reference. Loader, canonicalizer, TF-IDF/int8 MLP, classifier, bootstrap và UI đều dùng implementation Hy; không viết adapter thay Hy. Model/manifest/PSL lấy đúng gói Phúc. Mã sản phẩm và frozen artifacts không sửa.

Môi trường: Windows, CPython 3.11.14, Flutter 3.47.9/Dart 3.13.7; emulator `Medium_Phone_API_37.0`, Android 17/API37/x86_64. Student `student-mlp-kd-int8-v1`, threshold `0.72961075`, quy tắc `score >= threshold`, sigmoid chưa hiệu chuẩn. Teacher vẫn là engine mặc định; Student có nút thử nghiệm riêng.

| Kiểm tra đã chạy | Kết quả thực tế |
| --- | --- |
| QA bundle/Python chạy lại | 86 passed, 0 failed, 0 skipped |
| Flutter analyze app Hy | No issues found |
| Flutter tests gốc của Hy | 54 passed, 0 failed, 0 skipped |
| Dart package regression | 294 passed, 0 failed, 0 skipped |
| QA implementation trên Windows host | **79 passed, 0 failed, 0 skipped**, 79 ca nghiệp vụ |
| QA cùng implementation trên Android profile, tắt mạng | **79 passed, 0 failed, 0 skipped**; setup/teardown framework không tính vào 79 |
| Shared Python reference trên cả host và Android | **54 classified/9 rejected**, nhãn và canonical text khớp, score delta lớn nhất **`5.551115123125783e-17`** |
| Metadata/asset/edge cases | Version/threshold/hash/model/PSL; zero TF-IDF; biên bằng ngưỡng tổng hợp; 9 kiểu lỗi asset/manifest đều đạt |
| Android inference, 270 mẫu sau 5 warm-up | p50 **0,035 ms**, p95 **0,111 ms**, mean **0,06416 ms**; gồm validate/canonicalize/TF-IDF/MLP, không gồm UI |
| Loader MLP trong process Android profile | **27,819 ms**; khác với thời gian mở cả app |
| APK release nguyên bản và offline smoke | Build đạt; kiểm hash model/PSL nằm trong APK, cài app, force-stop/mở lại ba lần với PID khác nhau, thao tác UI Teacher/Student thật đạt |

Ba lần mở release là khởi động nguội theo process; vẫn có filesystem/shader cache và thời gian quan sát UI có overhead ADB. APK là bản universal chứa cả Teacher/Student; RAM/PSS là toàn app, không phải riêng tensor MLP. Số đo chi tiết, môi trường, hash APK và từng lần mở nằm trong [`student_mlp_release.json`](tables/week7/student_mlp_release.json). Chỉ nghiệm thu emulator x86_64, chưa chạy điện thoại vật lý/ARM64. Trạng thái mạng được lưu trước/trong/sau và khôi phục sau mỗi lượt.

**QA-W7-MLP-01 — đã sửa và xác minh tại `f817ec9`:** mở app mới, nhập `http://example.com:99999/`, bấm **Phân tích bằng Student**. Classifier trả `Unclassifiable` và UI nay hiện thông báo từ chối/mã `invalid_url`; luồng URL hợp lệ vẫn hiện nhãn/score/model. Regression giữ nguyên trước/sau bản sửa và đạt trên host lẫn Android emulator. Bản `feb5763` trước đó đạt 78/79 do không render outcome lỗi; số liệu thất bại được giữ tại `student_mlp_verification.json::history_before_ui_fix`. QA không sửa UI thay Hy.

CI giữ bốn job hiện có; checkout Hy ghim **`f817ec9`** và chạy đủ 79 host tests trong job Student Ubuntu/Windows. Actionlint, 26 Bash steps và 14 tình huống chọn source được kiểm tại máy; host gate đạt với bản sửa. **Chưa có Actions mới cho các thay đổi chưa commit/push**. Kết quả 14/14 cũ thuộc `68e7a6b`, không nghiệm thu thay đổi này; người dùng cần push và xác nhận checks trên đúng commit QA mới.

Bằng chứng: [`student_mlp_dart.json`](tables/week7/student_mlp_dart.json), [`student_mlp_android.json`](tables/week7/student_mlp_android.json), [`student_mlp_android_results.json`](tables/week7/student_mlp_android_results.json), [`student_mlp_release.json`](tables/week7/student_mlp_release.json), [ảnh release offline](figures/week7/student_mlp_android_offline.png). Các lệnh để người khác chạy lại nằm ở mục implementation MLP trong [`tests/README.md`](../tests/README.md).


## Kiểm lại HEAD Hy `680a8bd` ngày 22/11/2026

PR #33 chỉ đổi `mobile/tool/sync_assets.sh` và hai tài liệu so với `f817ec9`; mã inference/UI/config Android giữ nguyên. Kiểm lại đúng source **`680a8bd8806db337d8a8c039c0c3c5705b26c061`**, Student **`bc3a3a7054e2f6e6e733595f40f38439784536a1`**. Bản clean integration là checkout main **`4d13bee8738e387a68376b8d78dfff91916172aa`** rồi áp diff PR #33 lên working tree; không tạo merge commit. Clone mới không tái dùng output build/assets, có tái dùng cache SDK/Gradle/Pub. Đối chiếu 51 file sản phẩm/config khớp source Hy, bỏ khác biệt CRLF/LF ở file text.

| Kiểm tra thực tế | Kết quả |
| --- | --- |
| Asset sync khi không có ref `refs/remotes/pr/35` | Lấy Student từ artifacts đã có trong repo; Teacher, Student và PSL đạt size/SHA-256 |
| Model hỏng / thiếu artifacts và không có ref fallback | Model hỏng bị từ chối; thiếu artifacts trả lỗi rõ và gợi ý fetch. Phục hồi model rồi sync lại đạt |
| Flutter analyze / tests / Dart package tests trên clean candidate | Sạch; **54/0/0** Flutter, **294/0/0** Dart |
| Host QA implementation Hy tại HEAD mới | **79/0/0**; 54 hợp lệ + 9 rejected; max delta **`5.551115123125783e-17`** |
| Android emulator QA tại HEAD mới | **79/0/0** nghiệp vụ; parity 54/9 đạt; loader/UI lỗi và Teacher default/Student optional đạt. Hai sự kiện setup/teardown không cộng vào 79 |
| APK release từ clean candidate | Build thành công, **50.136.027 bytes**, hash trong JSON; không nhận là APK riêng Student |
| Offline release | Ba lần force-stop/mở lại, Teacher/Student inference thật đạt; airplane bật, Wi-Fi/data tắt, không default route IPv4/IPv6; trạng thái mạng ban đầu được khôi phục |

Hai ghi chú không chặn chức năng: handoff của Hy dòng 5 ghi Khiêm là người triển khai, cần tách Hy triển khai/Khiêm QA; Git Bash Windows thiếu `shasum` nên dòng in hash brand trống, nhưng hash Teacher/Student/PSL bằng Python vẫn được kiểm bắt buộc. QA đối chiếu brand bằng Python khớp hash frozen `6d434533e479f0f2e1d2602af72f54a1d15677961540684834536ae5d94fbee6`.

Kết quả đủ để đề xuất approve PR #33 trong phạm vi Windows/Android emulator đã kiểm; không tự gửi review hoặc đóng Issue #29/#31. Vẫn chưa nghiệm thu điện thoại vật lý/ARM64. Bằng chứng mới: [`hy_head_recheck.json`](tables/week7/hy_head_recheck.json). Các JSON/screenshot tại `f817ec9` được giữ nguyên để truy nguyên; không gán lại revision cho kết quả cũ. CI pin Hy đã chuyển sang `680a8bd`; Actions cho thay đổi này cần người dùng push và xác nhận sau đó.
