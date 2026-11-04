# V1 nested/calibrated — lưu lịch sử

Bản này là kết quả đã chạy trước khi đổi sang notebook v2 dễ đọc. Không phải đường chạy chính cho sinh viên.

- Báo cáo v1: week5_models.md vàweek5_validation.md trong thư mục này.
- Notebook v1: notebooks/archive/05_nested_v1.ipynb.
- Config v1: configs/archive/e2_models_nested_v1.toml; configs/e2_models.toml ởroot cũng được ghi rõ làv1.
- Các bảng05 cũ, hình05 cũ và models/week5_lexical_models.joblib không bị ghi đè. Chúng khác namespace05_readable của v2.
- experiments.py/week5_reporting.py và tests cũ vẫn giữ làm code tham khảo; không cần đọc trước khi hiểu notebook v2.

Bản sao chính xác source/config/notebook/handoff/model v1 trước khi sửa nằm trong ZIP local `data/interim/week5_nested_v1_snapshot.zip`, SHA ởsnapshot.json. ZIP bịGitignore; muốn tái lập lịch sử trên máy hiện tại có thể giải nén vào thư mục riêng, chạy từ root đó bằng cùng môi trường thư viện. Không giải nén đè project hiện tại. Dataset gốc không cần cho runner v1 vì ZIP đã giữ bốn bảng handoff.

Sourcehash trong metadata v1 mô tả code tại thời điểmv1, không hứa khớp CLI v2 đã thay đổi. Không sửa SHA cũ để làm metadata có vẻ mới.
