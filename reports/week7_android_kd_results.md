# Chọn Student để thử offline trên Android

**Đề xuất cho Hy:** tích hợp thử **LightGBM KD 200 cây, 15 lá, learning rate 0,10**. Mô hình dùng cùng định dạng cây, bộ TF-IDF và 20 đặc trưng E2 với bản 400 cây của nhóm. Khi giảm một nửa số cây, AP theo fold chỉ chênh −0,000018. Gói dữ liệu giảm từ 1.249.389 xuống 769.530 byte. Bản ZIP bàn giao 133.292 byte đã gồm cả manifest và ca kiểm thử.

**Nếu nhóm chấm theo AP trên Train Group CV**, Student KD dẫn đầu là **mô hình tuyến tính cộng điểm từ ký tự URL và E2**, AP 0,93457. Ở cùng 110 cảnh báo nhầm trên dự đoán ngoài fold của Train, nó bắt thêm 101 URL phishing so với LightGBM KD 200 cây. Bản học nhãn thật của chính kiến trúc này còn tốt hơn. Nhóm có thể giải thích riêng hai câu hỏi “kiến trúc nào tốt” và “KD giúp được bao nhiêu”.

## Đã thử gì

- **LightGBM.** So ba cấu hình 200 cây × 15 lá với tốc độ học 0,05 hoặc 0,10 và 300 cây × 15 lá với tốc độ 0,05. Mỗi cấu hình so nhãn thật với KD học trung bình nhãn thật và điểm Teacher. Mốc gốc là bản 400 × 15 ở tốc độ 0,05. Khi giữ tốc độ 0,05, AP KD chỉ đạt 0,90995 với 200 cây và 0,91598 với 300 cây. Việc tăng tốc độ học lên 0,10 mới giúp bản 200 cây đạt 0,91855 trong phép thử này.
- **Student cộng điểm.** Mỗi đoạn 2–5 ký tự của URL có một trọng số, mỗi khoảng giá trị của 20 đặc trưng E2 có một điểm cộng. Mô hình cộng các điểm rồi dùng sigmoid. Khi huấn luyện, các đoạn ký tự xuất hiện với tần suất khác nhau rõ rệt giữa hai lớp được tăng trọng số trước khi fit. Trọng số này được gộp sẵn vào hệ số xuất ra. Thử 8.192 và 16.384 đoạn ký tự. Bản KD 16.384 cho AP cao hơn trên ba fold.
- **Student băm ký tự.** Đưa từng đoạn ký tự vào một trong 32.768 hoặc 65.536 ô bằng phép băm cố định, rồi tính một tích vô hướng. Mô hình chỉ đọc chuỗi URL, bỏ qua nhánh E2. Bản 65.536 ô đứng đầu hai cấu hình của họ này trên Train. Đây là bản nhanh nhất trong phép đo Python.
- Với hai Student tuyến tính, đối chứng hard học nhãn thật bằng binary cross-entropy. KD kết hợp 50% loss nhãn thật với 50% loss Teacher ở nhiệt độ 2, có nhân hệ số T². Mỗi cặp giữ nguyên đầu vào, cấu hình và ngân sách tối ưu.

## So trên cùng dữ liệu

13.078 URL Train, 2.074 phishing, chia ba fold theo tên miền. Mỗi fold dùng điểm của Teacher chỉ từng fit trên phần fitting của fold đó. Các điểm Teacher trên phần fitting là in-sample. Khi fit Student cuối trên toàn Train, dùng điểm của Teacher stacking v2 phát hành. Từ vựng, IDF, các trọng số dùng nhãn và ranh giới E2 chỉ học trên phần fitting. Các lượt này dùng thuật toán xác định hoặc seed 42 với một luồng.

AP chính là trung bình AP của ba fold. Trong mỗi họ, chọn cấu hình KD theo AP này rồi lấy bản hard cùng cấu hình. Mỗi bản khóa ngưỡng riêng từ dự đoán ngoài fold (OOF) của Train với ngân sách FPR 1%. Cột OOF bên dưới cùng có 110 cảnh báo nhầm, thuộc chính dữ liệu đã dùng để đặt ngưỡng.

| Student | CV AP | OOF bắt được / 2.074 | Validation AP | Validation bắt được / 24 | Báo nhầm / 1.561 |
|---|---:|---:|---:|---:|---:|
| LightGBM 200 hard | 0,91775 | 1.484 | 0,6531 | 13 | 10 |
| LightGBM 200 KD | 0,91855 | 1.482 | 0,6596 | 13 | 10 |
| Cộng điểm 16k hard | **0,93661** | **1.609** | 0,5401 | 15 | 16 |
| Cộng điểm 16k KD | **0,93457** | **1.583** | 0,5617 | 14 | 16 |
| Băm 65k hard | 0,92172 | 1.501 | 0,4135 | 11 | 24 |
| Băm 65k KD | 0,91989 | 1.481 | 0,4113 | 11 | 17 |

Hai mốc đã lưu là **LightGBM KD 400** với CV AP 0,91857, Validation AP 0,6549, bắt 13 và báo nhầm 10. **Teacher stacking v2** đạt CV AP 0,93067, Validation AP 0,5549, bắt 15 và báo nhầm 14 tại ngưỡng phát hành.

## Có thể quy phần tăng nào cho KD?

Bootstrap ghép cặp 1.000 lần, lấy mẫu theo tên miền trong từng fold, giữ nguyên cặp điểm của mỗi URL. Khoảng 95% dưới đây có điều kiện trên các mô hình đã fit và bộ fold đang dùng.

| Kiến trúc | Δ CV AP của KD so với bản hard | Khoảng 95% |
|---|---:|---:|
| LightGBM 200 | +0,00080 | [−0,00062, +0,00223] |
| Cộng điểm 16k | −0,00204 | [−0,00356, −0,00058] |
| Băm 65k | −0,00183 | [−0,00339, −0,00055] |

Bản cộng điểm KD hơn LightGBM 200 KD **0,01602 AP** trên cùng fold, khoảng [0,01003, 0,02285]. Khi so với chính bản cộng điểm hard, KD làm AP giảm ở cả ba fold. Với LightGBM, khoảng của chênh lệch KD–hard chứa 0. Nhóm có bằng chứng tốt hơn cho việc nén số cây mà vẫn giữ chất lượng so với bằng chứng KD giúp bản 200 cây vượt mô hình cùng cấu hình.

Validation đã được xem trong các tuần trước và chỉ có 24 phishing. Tại ngưỡng khóa, bản cộng điểm KD bắt được 4 phishing mà LightGBM 200 KD bỏ sót, đồng thời bỏ sót 3 phishing mà LightGBM bắt được. Cả 24 phishing Validation đều cùng nguồn, 15/16 cảnh báo nhầm của bản cộng điểm thuộc Tranco. Kết quả cần được đọc trong giới hạn của bộ dữ liệu và các cấu hình đã thử. Official Test và external chưa được dùng trong nghiên cứu này.

## Chi phí và bàn giao

Đo xen kẽ bốn bộ suy luận trên Windows, một luồng, 250 URL giống nhau, 30 lượt làm nóng mỗi mô hình, hai lượt đo mỗi URL. Thời gian từ chuỗi URL thô đến score, loại thời gian khởi tạo model khỏi phép đo. Dung lượng là model và các tài nguyên dữ liệu cần cho inference, chưa tính runtime.

| Model KD | Dữ liệu chạy, byte | p50 Windows, ms | p95 Windows, ms |
|---|---:|---:|---:|
| LightGBM 400 | 1.249.389 | 4,99 | 6,48 |
| LightGBM 200 | 769.530 | 3,19 | 4,60 |
| Cộng điểm 16k | 830.180 | 1,01 | 1,65 |
| Băm 65k | 341.716 | 0,14 | 0,24 |

Mỗi ZIP bên dưới có model, dữ liệu tiền xử lý cần thiết, manifest SHA-256 và 58 URL tham chiếu (52 hợp lệ, 6 đầu vào cần từ chối). Bản LightGBM có cả vocabulary/IDF riêng. Kết quả xuất khớp nhãn Python trên toàn bộ 1.585 URL Validation của từng bản.

- [LightGBM 200 KD — gói cho Hy](../artifacts/android_kd_handoff/boost200.zip). Ngưỡng 0,6138319444287572. Dùng `features.json` để tính TF-IDF ký tự và nối E2 theo đúng thứ tự rồi duyệt cây trong `kd_mixed.json`.
- [Student cộng điểm 16k KD — đối chứng ưu tiên AP](../artifacts/android_kd_handoff/additive16k.zip). Ngưỡng 0,592151468193935. Giữ cách duyệt Unicode theo code point và thứ tự chuẩn hóa TF-IDF như Python. Chọn khoảng E2 bằng số mốc nhỏ hơn **hoặc bằng** giá trị đầu vào.
- [Bảng số liệu, khoảng tin cậy và hash hai gói](tables/android_kd_comparison/). Bàn giao này đã kiểm Python. Máy local chưa có Android runtime hoạt động để kiểm score trên thiết bị, p95, RAM hoặc kích thước APK. Hai gói dùng cho tích hợp thử.

Chạy từ thư mục gốc với môi trường dự án. Hai lệnh đầu dùng ZIP có sẵn, chạy offline cả khi không tải Teacher. Các lệnh còn lại tái lập các lượt huấn luyện và phép so sánh.

```powershell
.\.venv\Scripts\python.exe scripts/compare_android_kd.py --model boost200 --predict "https://example.org"
.\.venv\Scripts\python.exe scripts/compare_android_kd.py --model additive16k --predict "https://example.org"
.\.venv\Scripts\python.exe scripts/experiment_android_boost.py
.\.venv\Scripts\python.exe scripts/experiment_android_additive.py
.\.venv\Scripts\python.exe scripts/experiment_android_hash.py
.\.venv\Scripts\python.exe scripts/compare_android_kd.py
```
