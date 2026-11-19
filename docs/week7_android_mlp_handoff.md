# Bàn giao MLP KD int8 cho Android tuần 7

Phúc bàn giao **student-mlp-kd-int8-v1** cho Hy tích hợp Android offline và Khiêm kiểm thử. Model dùng TF-IDF ký tự và một lớp ẩn 64 nút. Artifact được fit trên toàn bộ Train với 13.078 URL Gold/Silver và 8.192 URL Bronze. Teacher stacking v2 phát hành cấp điểm mềm trong lúc huấn luyện.

## Gói inference

| File | Nội dung |
|---|---|
| [student_mlp.json.gz](../artifacts/student_mlp_android/student_mlp.json.gz) | JSON nén GZIP chứa vocabulary/IDF, trọng số int8 lớp đầu, scale theo nút ẩn, bias và trọng số tầng cuối. 283.334 byte. |
| [manifest.json](../artifacts/student_mlp_android/manifest.json) | Phiên bản, SHA-256 của model và PSL, ngưỡng, quy tắc quyết định và provenance. |
| [PSL đóng băng](../mobile/packages/phishguard_features/assets/psl_icann_tldextract_5.4.0.txt) | Bảng suffix cần cho parser offline. Dùng đúng bản mà manifest pin hash. 75.007 byte. |
| [python_reference.json](../artifacts/student_mlp_android/python_reference.json) | 54 URL tổng hợp có score/nhãn chuẩn và 9 đầu vào cần từ chối. Dùng cho QA. |
| [verification.json](../artifacts/student_mlp_android/verification.json) | Kết quả đối chiếu Python trực tiếp trên 13.078 URL Train. |

Dữ liệu model và PSL tổng cộng 358.341 byte theo hai file ở định dạng lưu trên repo. APK, thời gian nạp, độ trễ và RAM trên Android cần số đo thiết bị. Android chỉ dùng hai asset inference cùng manifest và các hàm tiền xử lý. Điểm sigmoid chưa được hiệu chuẩn.

### Luồng suy luận cho Hy

1. Kiểm bản ghi kích thước và SHA-256 của model nén và PSL trong manifest. Giải nén GZIP rồi đọc JSON UTF-8.
2. Kiểm URL bằng parser offline. Chuẩn hóa như `student_text()` của Python: IDNA hostname, bỏ scheme/userinfo/fragment, chuẩn hóa port mặc định theo scheme, giữ nguyên case và ký tự escape của path/query. Mỗi đoạn từ hai ký tự trắng liên tiếp trở lên được thay bằng một dấu cách. Đầu vào rỗng, ký tự điều khiển, khoảng trắng hai đầu hoặc URL sai quy tắc cần trả lỗi phân loại.
3. Duyệt Unicode **code point**, đếm n-gram ký tự từ 3 đến 5. Chỉ dùng mục có trong `terms`. Giá trị mục `i` là `(1 + ln(count_i)) × idf_i`. Chia vector cho chuẩn L2 nếu chuẩn khác 0.
4. Giải mã `weights_int8_base64` thành **262.144 byte có dấu**. Layout là `4096 × 64`, theo thứ tự term rồi đến nút ẩn. Phần tử ở `i*64+j` cần nhân `hidden_scales[j]` để suy ra trọng số. Tính `hidden_j = ReLU(dot(tfidf, W[:,j]) + hidden_bias[j])`, rồi `score = sigmoid(dot(hidden, output_weight) + output_bias)`.
5. Với URL hợp lệ không có term khớp, dùng vector TF-IDF 0 và vẫn tính hai lớp bias. Trả class 1 nếu `score >= 0.72961075`, class 0 nếu thấp hơn. Lấy ngưỡng từ manifest khi tích hợp.

### Bằng chứng và kiểm thử cho Khiêm

- Kiểm 63 ca từ file reference. Score cần khớp Python trong sai số tuyệt đối **2 × 10⁻⁶**. Nhãn cần khớp chính xác. Các ca `rejected` phải trả trạng thái lỗi.
- Thử làm hỏng file nén hoặc manifest để chắc app báo lỗi nạp. Kiểm mất mạng, khởi động nguội và các ca Unicode, IDNA, IPv6, percent escape và ngưỡng.
- Python đã so đường raw URL → score với phép tính trực tiếp trên ma trận TF‑IDF/int8 trên **13.078 URL Train**. Sai số lớn nhất dưới `3 × 10⁻¹⁶` và **0 nhãn lệch**. Đây là kiểm tra suy luận Python, còn Android sẽ được đối chiếu khi Hy nối model vào app.
- Ngưỡng `0.72961075` khóa từ pooled **Train Group OOF int8 seed 49**, ngân sách FPR 1%. Ở OOF để đặt ngưỡng có 1.415 true positive và 110 false positive. Kết quả AP **0,90207** là mean-fold Group CV qua ba seed của nghiên cứu. Full-Train artifact dùng toàn bộ Train và cần được đánh giá riêng khi có tập kiểm tra được phép dùng.

## Chạy tham chiếu

```powershell
python scripts/prepare_android_mlp.py --predict "https://example.org/Report?Q=%2F"
python -m pytest -q tests/test_android_student_mlp.py
```

Để tái tạo artifact, dùng Python 3.11 với bộ dependency Teacher đã khóa, cùng một checkout nghiên cứu tại commit `8389b371728d4aab8246c0cf9606eb788a8e0365`. Runner tái sử dụng đúng hàm huấn luyện đã chạy trong nghiên cứu và kiểm hash các input. [Nhánh nghiên cứu](https://github.com/phuctran33/PhishGuardVN/tree/research/student-bronze-kd)

```powershell
python scripts/prepare_android_mlp.py --research-root D:\PhishGuardVN
```
