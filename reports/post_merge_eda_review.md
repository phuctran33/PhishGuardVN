# Đối chiếu EDA/preprocessing sau merge PR #12 và #13

Revision được kiểm tra: main `d7a5a6644a6118690c6e8306b6c66e181e08e361`. PR #12 đã merge tại `83ccbb3`, PR #13 tại `d7a5a66`; PR #7 cũng đã merge tại `b7c5b16`. Đây là bản cập nhật diễn giải/provenance, không phải lần tính EDA hay thí nghiệm mới.

## Các điểm đã xác nhận và sửa

1. `data_report_final.md` trước đây nói cả 167 external còn pending mà chưa phân biệt hai CSV nguồn với ledger sau PR #13. CSV nguồn vẫn đúng là 167 pending, nhưng ledger có 99 verified theo bằng chứng tài liệu hostname lịch sử, 68 pending, 0 rejected. Đã sửa phạm vi phát biểu, giữ nguyên mọi bảng/số đo EDA.
2. Câu “PR #7 còn mở” đã lỗi thời; đã cập nhật trạng thái merge. Human error analysis H5.2 và external K5.3 là hai tập khác nhau, không ghi đè checklist H5.2.
3. Sau PR #13, Hưng xác nhận trong hội thoại đã kiểm tra lại 99 trường hợp và đồng ý với nhận xét. Cách trình bày hiện tại là **99 human-checked (92 phishing/7 benign), 68 pending**. [Bản xác nhận](annotations/k53_human_check_confirmation.csv) liên kết đúng 99 ID và candidate signature; ghi thời điểm nhận xác nhận, không tự bịa ngày kiểm tra thực tế. Đây là tự báo cáo theo nhóm của reviewer, không phải một lần kiểm tra độc lập mới do công cụ chứng kiến. Không mở rộng sang live-site/full URL hoặc 68 pending.
4. Hai mục E2 verifier là FAIL thực tế, exit 1, không phải warning vô hại hoặc PASS toàn bộ. Nguyên nhân và đề xuất sửa riêng bên dưới; không thay verifier, manifest E2, reference, dictionary hoặc ma trận để che lỗi.

## Trạng thái external và lịch sử review

| Lớp thông tin | Trạng thái đúng |
|---|---|
| Hai CSV nguồn 15 cột | 167 candidates = 138 phishing/29 benign; 167 pending nguyên trạng |
| Ledger `derived/k53_candidates.csv` của PR #13 | 99 verified theo tài liệu hostname lịch sử, 68 pending, 0 rejected; giữ method/reviewer của lần xuất đó |
| Xác nhận human check bổ sung của Hưng | 99 human-checked, theo ID/signature riêng; tự báo cáo đồng ý với 99 nhận xét có sẵn |
| Số human được ghi trong snapshot producer PR #13 | 0 tại thời điểm xuất; không sửa ngược lịch sử thành một lần human review đã xảy ra trước đó |
| Benchmark/inference external | PREPARED/BLOCKED; chưa có Teacher finalized, metrics=null, n_evaluated=0 |

Không dùng “AI-verified” làm nhãn trạng thái hiện tại trong phần bàn giao. Bản ghi phương pháp của lần đối chiếu tài liệu ban đầu vẫn được giữ để truy vết; không đổi đồng loạt reviewer thành Hưng, không biến ngày xác nhận thành ngày đọc từng tài liệu. Bản xác nhận mới không sửa `review_status`, `review_method` hoặc nhãn của ledger cũ. Việc human check không bảo đảm nhãn hiện tại, credential phishing ở mọi host, quyền sử dụng hay source independence.

13/13 nhóm nguồn vẫn chỉ một nhãn. Host-only đã thống nhất format cho hai lớp nhưng không chứng minh loại hết source/campaign bias. Do đó chỉ chuẩn bị recall pilot trên subset phishing có bằng chứng, theo nguồn, sau khi nhận Teacher đúng schema/reference và provenance Core Group CV; không suy ra FPR/generalization chính thức. Không train/tune trên external hoặc dùng nhãn Official Test cho lựa chọn.

## Hai FAIL của E2 freeze verifier

Chạy script nguyên trạng trên main sạch, trước khi sửa tài liệu:

```sh
python scripts/05_verify_e2_artifacts.py
```

Không có CSV local: **34/36 checks đạt, 2 FAIL**, 2 thông báo SKIP đối chiếu ma trận local. Với bản sao Train+Validation handoff đang có sẵn, không tái tạo hay sửa bytes: **35/37 checks đạt, 2 FAIL**, 1 SKIP do không có ma trận `all` local. Đây là SKIP của CLI, tách biệt pytest. Reference, schema, frozen/git_dirty lúc xuất, dictionary hashes, feature order, tldextract, trainval Test-exclusion và parity đều đạt.

Hai FAIL nằm ở cùng guard `verify_manifest()` của `scripts/05_verify_e2_artifacts.py`, một lần cho mỗi manifest. Guard lấy mọi đường dẫn khác nhau giữa freeze commit `45908a693256d3124a64b02b5fd590a36f1535ad` và HEAD, rồi chỉ cho phép `reports/tables/` hoặc parity JSON. Vì vậy `.gitattributes`, README, modeling configs, external data/docs và code audit mới cũng bị coi là thay đổi producer E2. Output chỉ in 5 đường dẫn đầu, không phải toàn bộ nguyên nhân.

Đối chiếu trực tiếp Git blob tại freeze commit với main và hash trong EDA manifest cho thấy **7/7 file producer/reference/dictionary byte-identical**: `url_parser.py`, `features.py`, `brand_features.py`, `brand_reference_v1.csv`, hai feature dictionaries, `05_build_matrix_x_brand.py`. `05_make_parity_vectors.py` và package initializer cũng không đổi; parity được script tái tạo giống hệt. Các input có hash trong EDA manifest, gồm splits và Train+Validation handoff local, đều khớp. Đây là bằng chứng chưa có artifact-affecting drift được phát hiện trong phạm vi đã đối chiếu, không phải lý do vô hiệu hóa provenance.

**Đề xuất cho PR verifier riêng; chưa triển khai trong PR tài liệu này:**

- Thay guard theo toàn repository bằng kiểm tra bytes tại freeze commit của tập producer và dependency thực sự; bao gồm package initializer và local import closure. Không bỏ kiểm tra cả `src/`, không đơn giản thêm whitelist mọi `.py`/`.csv` hay đổi FAIL thành warning. Thay đổi import/producer phải làm guard fail, kể cả thay đổi chưa làm parity fixtures đổi.
- Giữ nguyên hash reference/hai dictionary, version/schema/order, frozen/clean provenance, commit tồn tại, Test-exclusion của trainval và parity regeneration. Kiểm tra input/split hash theo phạm vi manifest; trainval chỉ đọc train/val. Git lỗi, thiếu producer/commit hoặc dependency chưa phân loại phải fail rõ, không coi stdout rỗng là “không thay đổi”. Không sửa manifest freeze để trỏ vào HEAD mới chỉ nhằm pass.
- Bắt buộc mutation tests: docs/external inventory không liên quan được phép; sửa parser, công thức feature, reference, dictionary, builder, dependency/import hoặc input/split đã ghim phải fail; deletion và lỗi Git cũng fail. Cần ca sửa công thức ở nhánh chưa có parity fixture để chứng minh guard không chỉ dựa vào parity. Giữ dirty-check và các tests hiện có. Đây là tiêu chí nghiệm thu bản sửa tương lai, không tuyên bố các tests đó đã chạy trong lượt này.

Do chưa sửa logic verifier nên **không có PR code verifier** trong bàn giao này; hai FAIL vẫn được báo nguyên trạng. Chúng không chứng minh phải tính lại EDA hoặc thay frozen artifacts. Nếu triển khai đề xuất thì tách PR, không gộp vào cập nhật tài liệu.

## Đối chiếu với `ml-data.pdf` và §14

Đã đọc bản local `/Users/nguyenduchung/Downloads/ml-data.pdf`, 3 trang. SHA256: `bdca1f269200cb77ed591a5e669af50e05d44077b58b952f8b3a4155282def63`. Không đưa PDF của thầy vào repository. PDF yêu cầu bài toán/nguồn/thu thập/làm sạch ở trang 1, chất lượng/lưu trữ/EDA ở trang 2, EDA phi cấu trúc ở trang 3. Checklist 21 mục chia nhỏ các yêu cầu này; domain/source/Train-only là kiểm soát bổ sung phù hợp bài toán, không được trình bày như lời nguyên văn của rubric.

| Mục §14 | Trang PDF / phạm vi | Bằng chứng hiện có | Kết luận |
|---|---|---|---|
| 1 | 1: bài toán | Report §1–3, datasheet | Đủ |
| 2 | 1: nguồn, phương pháp/công cụ/định dạng | Report §2–3, data_sources.md, attribution tác giả | Đủ trong phạm vi dataset có sẵn; không nhận công crawl gốc |
| 3a | 1: noise/duplicates | duplicates.csv, notebook 01/02 | Đủ |
| 3b | 1: missing, chuẩn hóa, dtype | metadata_inventory.csv, report §5 | Đủ; không impute nhãn/thời gian |
| 3c | 1: quy trình xử lý | preprocessing_flow.csv, excluded_rows.csv | Đủ; công khai 2 unresolved Domain |
| 4a | 2: tiêu chí và tự động kiểm tra | Notebook 03 guards, tests split/report | Đủ; hai FAIL verifier được công bố riêng |
| 4b | 2: thủ công/tự động và giới hạn | Report §5/12, datasheet, H5.2; human check external bổ sung riêng | Đủ mô tả; không nhận audit nguồn là nhóm tái làm |
| 5 | 2: lưu trữ/quản lý | Data README, manifest và verification | Đủ; snapshot chạy và cập nhật tài liệu phân biệt |
| 6a | 2: mẫu/thuộc tính/missing/nhãn | class_populations.csv, metadata_inventory.csv, report §6 | Đủ |
| 6b | 2: moments/range/IQR | lexical_descriptive.csv, report §7 | Đủ; ddof và quantile được nêu |
| 6c | 2: phân bố từng thuộc tính | lexical_distributions.csv, notebook 02 quantile/boxplot | Đủ |
| 6d | 2: correlation | lexical_spearman.csv, correlated_pairs.csv, report §10 | Đủ |
| 6e | 2: multicollinearity/ý nghĩa | lexical_vif.csv, report §10; hằng/thưa §7–8 | Đủ; không tự feature selection |
| 6f | 2: outlier/kế hoạch xử lý | lexical_iqr_outliers.csv, report §11 | Đủ; giữ giá trị hợp lệ |
| 6g | 2: EDA các thuộc tính E2 | brand_descriptive.csv, brand_value_counts.csv, report §8 | Đủ; đúng v1, chỉ Train |
| 7a | 3: độ dài văn bản | url_structure.csv, report §9 | Đủ cho modality URL |
| 7b | 3: keyword | keyword_frequencies.csv, report §9 | Đủ; không bịa support khi chỉ ít keyword phổ biến |
| 7c | 3: ký tự đặc biệt/nhiễu | url_structure.csv, report §9/12 | Đủ |
| 8 | 1–2: nhất quán/chất lượng; kiểm soát leakage bổ sung | domain_overlap.csv, fold_summary.csv, integration test | Đủ trong scope domain đã resolve |
| 9 | 1–2: nguồn/missing/chất lượng; bias bổ sung | source_labels_train.csv, timestamps.csv, notebook 05 | Đủ phát hiện và công bố; chưa loại bias |
| 10 | 1–3: báo cáo có bảng/biểu đồ/nhận xét | data_report_final.md, 3 hình hiện có, các bảng đã lưu | Đủ |

Không có ảnh/âm thanh làm dữ liệu đầu vào nên các ví dụ EDA ảnh/âm thanh ở trang 3 không áp dụng. Rubric không đòi train thêm model hoặc có benchmark external chính thức trong báo cáo dữ liệu này. Không phát hiện thiếu sót EDA cần viết thêm code, notebook hoặc biểu đồ. **Phần EDA/preprocessing đã bao phủ 21/21 mục theo bằng chứng hiện có**, trong phạm vi/giới hạn đã công bố; không cam kết điểm chấm.

## Kiểm thử, bảo toàn và tái lập

Kết quả chạy thực tế, hash bảo toàn và phạm vi SKIP được lưu tại [post_merge_eda_verification.json](tables/data_report/post_merge_eda_verification.json). Không Run All lại vì không sửa notebook hoặc tính toán; đã đọc code/saved outputs và kiểm tra các tests liên quan. Notebook 02/03/05 có execution count cho mọi code cell và không có saved error; notebook 01 có 6/7 code cell có execution count (cell 01-cell-10 không có trong bản committed). Không coi việc đọc saved outputs là một lần Run All mới hoặc nhận đã thực thi cell đó trong lượt này; verification của lần chạy EDA trước được giữ riêng. Không thay raw/labels/splits/folds, extractor, model bytes, metrics, EDA CSV, hình hoặc notebook outputs.

`eda_report_manifest.json` vẫn giữ runtime base/input/code hashes của lần tính EDA trước; chỉ hash báo cáo và chú thích overlay tài liệu được cập nhật. Tương tự, manifest K5.3 ghi overlay bản xác nhận và hash báo cáo mới, không đổi snapshot ledger hay kết quả benchmark. Verification cũ là lịch sử lần chạy cũ, không sửa thành kết quả mới. Notebook/script sinh báo cáo vẫn mô tả snapshot producer; nếu tái tạo chúng, giữ bản đối chiếu này và áp lại diễn giải sau merge/xác nhận từ sidecar, không ghi đè lịch sử hoặc đổi số liệu EDA.
