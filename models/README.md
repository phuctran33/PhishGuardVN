# Local baseline artifacts

Sau khi chạy notebook 04 hoặc scripts/train_baseline.py:
- week4_lr_baseline.joblib: pipeline, feature names, threshold và cấu hình.
- week4_lr_baseline_metadata.json: scope, phiên bản thư viện, hash source/handoff và model.

Artifact chỉ fit core train. Official validation là báo cáo bổ sung; test chưa được dùng.
Model được bỏ qua trong Git; bàn giao riêng. Xem reports/week4_baseline.md trước khi diễn giải score.

Bản metadata có thể quản lý phiên bản nằm ở reports/tables/04_run_metadata.json.
Source hashes chuẩn hóa CRLF về LF; input hashes kiểm tra byte gốc của các handoff.
