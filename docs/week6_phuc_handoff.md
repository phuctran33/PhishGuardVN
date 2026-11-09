# Tuần 6 — Phúc: đọc code và nhận Teacher v1

## Bắt đầu review từ đâu?

1. Đọc reports/week6_teacher.md để biết đã chọn gì, số liệu và giới hạn.
2. Mở notebooks/06_teacher_v1.ipynb: code model/fit/predict nằm ngay trong notebook.
3. Đọc scripts/predict_teacher.py để xem cách load và dùng model mà không train.
4. Kiểm tra reports/tables/week6/comparison.csv, errors.csv và teacher_selection.json.

## Luồng notebook

| Bước | Làm gì? | Vì sao cần? |
| --- | --- | --- |
| Setup | Import, đường dẫn, seed | Dùng cùng môi trường/cấu hình |
| 1 — Data | Đọc X/y/domain/folds, chặn v0/sai ID/hash | Tránh học nhầm dữ liệu |
| 2 — Models | Khai báo LR/SVM/MLP/HistGB/RandomForest | Nhìn trực tiếp model được tạo |
| 3 — Helpers | Ba hàm ngắn: inner folds, score, metrics | Tránh lặp lại cùng phép tính |
| 4 — CV | Fit trong fitting, predict outer holdout | Mỗi mẫu có một dự đoán ngoài phần đã học |
| 5 — Selection | Xếp mean AP, chọn Teacher | Chưa dùng Validation/external |
| 6 — Final fit | Tìm cấu hình bằng Train CV, refit Train | Tạo model bàn giao |
| 7 — Errors | 12 lỗi, đủ FP/FN ở ba folds | Hiểu model sai ở đâu |
| 8 — Resources | Đo kích thước/tốc độ PC | Có thông tin đánh đổi tài nguyên |
| 9 — Save | Lưu model, kết quả, selection, lock | Bàn giao đúng phiên bản |
| 10 — Demo | Load và thử năm URL | Xác nhận inference dùng được |
| 11 — External | Phép thử host-only đã review | Quan sát thêm sau khi đã khóa Teacher |

Ba hàm chính dễ tìm:
- inner_splits: chia hai phần bên trong outer fitting và kiểm tra domain.
- ranking_scores: lấy probability hoặc margin SVM để tính AP.
- calculate_metrics: tính AP/precision/recall/F1/FPR và confusion counts.

Lời gọi học thật là search.fit hoặc clone(model).fit ở CV/final fit.
train_teacher.py chỉ mở và chạy notebook, không giấu một thuật toán train khác.

## Hưng và Hy nhận gì?

- models/week6_teacher_v1.joblib: chỉ Teacher MLP và reference snapshot; khoảng 44 KB, cho phép đưa vào repo để pull là có.
- configs/week6_teacher_lock.json: model nào, schema v1, threshold cố định, hash model/selection.
- reports/tables/week6/teacher_selection.json: lý do chọn theo CV, feature order, params, phiên bản thư viện và hash input.
- oof_predictions.csv.gz, validation_predictions.csv.gz, training_partitions.csv.gz: pandas.read_csv đọc trực tiếp, dùng kiểm tra ID/folds/leakage.
- comparison.csv/resources.csv: metric, độ trễ PC và kích thước; errors.csv: 12 lỗi thật.
- external_results.json cùng hai bảng predictions: phép thử riêng, pending không làm ground truth.

Không cần tạo ZIP hay gửi một bộ thư mục kết quả khác. Model không tự train lại lúc predict.

## Chạy dự đoán

Từ root repo, dùng đúng .venv:
~~~powershell
.\.venv\Scripts\python.exe scripts/predict_teacher.py --examples
.\.venv\Scripts\python.exe scripts/predict_teacher.py "https://example.com/login"
~~~

Cần dependencies như metadata (đặc biệt scikit-learn 1.9.1); cùng package source và reference v1. Dùng artifact của nhóm có nguồn rõ ràng. Không mở website đích.

Nếu load trong Python:
~~~python
import json
from pathlib import Path
from phishguard_vn.external_pilot import load_locked_teacher

root = Path.cwd()
lock = json.loads((root / "configs/week6_teacher_lock.json").read_text(encoding="utf-8"))
predict = load_locked_teacher(root, lock)
print(predict("https://example.com/login"))
~~~

## Tái tạo nếu cần, không bắt buộc trước khi review

Nếu đã có core, lexical X, domains và folds từ 01 → 03 → 02:
~~~powershell
.\.venv\Scripts\python.exe scripts/05_build_matrix_x_brand.py --partition trainval
.\.venv\Scripts\python.exe scripts/train_teacher.py
~~~

Builder tái tạo chỉ Train/Validation, không sửa raw/folds. Khi đang có file chưa commit, không thêm --freeze để ép provenance sạch; metadata phải ghi đúng trạng thái. Notebook Teacher kiểm tra schema/reference/input/dictionary và ID.

Nếu chưa có handoff, dùng luồng chuẩn bị có sẵn của dự án: 01, 03, build E2 trainval, 02. Lưu ý notebook 02 bản mới có cả phần EDA brand v1; guard freeze trong phần xuất EDA yêu cầu artifact đúng quy định của nó. Không sửa guard đó chỉ để chạy ML; dùng handoff đã kiểm chứng hoặc tái tạo EDA trên checkout sạch theo hướng dẫn báo cáo.

Khi chạy lại, model/lock/bảng tuần 6 được ghi lại. Dữ liệu/metrics tuần 5 không ghi đè. Nếu thay model/grid/data, đọc và cập nhật báo cáo cùng phân tích lỗi.

## Những điều cần hiểu khi review

- AP không phải accuracy. Cột pr_auc trong CSV đang chứa average_precision_score.
- LR balanced là một cấu hình của LR, không phải họ thuật toán hoàn toàn khác.
- Inner CV chọn tham số; outer CV chấm. Scaler ở trong Pipeline.
- MLP và HistGB AP gần nhau; đây là quyết định theo tiêu chí, chưa là bằng chứng hơn hẳn về thống kê.
- Teacher fit toàn Train không dùng để tạo soft targets rồi đánh giá OOF trên chính Train; KD phải làm theo fold ở bước sau.
- External: 167 candidates, 99 có review scope lịch sử, 68 pending; chỉ 7 benign nên metric hai lớp rất hạn chế.
- Quy tắc LF trong .gitattributes giữ hash text giống nhau giữa Windows/macOS; không thay giá trị URL/nhãn/reference.

## Trạng thái kiểm tra cần biết

Đã chạy notebook thật, 391 tests pass/1 skip, load/dự đoán năm URL trong thư mục chỉ có source + Teacher + lock/selection, không có dataset. OOF metrics tính lại khớp, 24 artifact/input cũ giữ nguyên hash. Xem reports/tables/week6/verification.json.

Lần kiểm tra trước commit ghi nhận verifier freeze cũ có 4 FAIL: dirty, hai guard toàn repo, và exact equality của entropy. Bộ 47 parity cases khớp trong tolerance 1e-6 (sai số max được ghi trong verification.json). Không sửa code verifier/fixture để làm xanh kiểm tra. Đây là việc riêng đã được nhận diện trên main, không được che thành PASS.

Kết quả external mới đọc ở reports/tables/week6/external_results.json. benchmark_status.json của K5.3 vẫn là snapshot trước Teacher, được giữ để không ghi đè audit cũ.

Runtime revision trong metadata là commit nền lúc chạy; dirty=true vì code tuần 6 chưa commit. Hash code cells/source xác định mã thực sự đã dùng. Không sửa revision thành commit mới sau này để giả rằng model đã chạy trên commit đó.
