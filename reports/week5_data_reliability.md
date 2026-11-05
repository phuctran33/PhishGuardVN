Week 5 — Source Audit và Data Reliability
Phạm vi: Kiểm toán dataset_url.csv bằng notebook 05_source_bias.ipynb.
Quy mô: 53.116 bản ghi, 29 cột.
1. Tổng quan dữ liệu
Hạng mục	Số bản ghi	Tỷ lệ
phishing	36.706	69,11%
benign	16.410	30,89%
Train	36.909	69,49%
Validation	7.266	13,68%
Test	8.941	16,83%


Nguồn lớn nhất là chongluadao với 33.823 bản ghi (63,68%). Các nguồn còn lại: tranco 5.993; tinnhiem_web 5.879; tinnhiemmang 2.587; tranco_vn 2.512; tinnhiem_org 2.026; openphish 296.
2. Kết quả kiểm tra
Kiểm tra	Kết quả	Đánh giá
Cột bắt buộc (id, url, url_norm, domain, source, label, split)	Đầy đủ	Đạt
ID trùng	0	Đạt
URL trùng	0	Đạt
URL chuẩn hóa trùng	0	Đạt
Nhóm có nhiều nhãn theo id, url, url_norm	0	Đạt
URL không phân tích được hostname	0/53.116	Đạt ở mức cú pháp
Domain xuất hiện ở nhiều split theo cột domain	0	Chưa phát hiện overlap ở mức kiểm tra này


Không phát hiện lỗi trùng lặp theo các khóa đã kiểm tra. Tuy nhiên, URL có hostname không đồng nghĩa website đang hoạt động hoặc URL an toàn; kết quả domain overlap cũng không loại trừ mọi trường hợp dùng chung hạ tầng hay chiến dịch.
3. Rủi ro cần chú ý
3.1. Source-label confounding — rủi ro cao
Cả 7 nguồn đều chỉ chứa một nhãn:
- Chỉ phishing: chongluadao, openphish, tinnhiemmang.
- Chỉ benign: tinnhiem_org, tinnhiem_web, tranco, tranco_vn.
Nguồn vì vậy gắn chặt với nhãn trong dataset. Mô hình có thể học dấu hiệu riêng của nguồn thay vì học đặc trưng tổng quát của phishing. Đây là hạn chế lớn khi diễn giải kết quả mô hình.
3.2. Cơ cấu nguồn khác nhau giữa các split
Ví dụ, chongluadao chiếm 64,0% train, 77,4% validation và 51,2% test. tinnhiem_web chiếm 9,1% train, 3,7% validation và 25,1% test. Vì từng nguồn chỉ có một nhãn, thay đổi cơ cấu nguồn cũng làm thay đổi cơ cấu nhãn/nguồn giữa các split. Nên báo cáo thêm kết quả theo nguồn, không chỉ dùng một chỉ số tổng thể.
3.3. Độ tập trung domain
Phần lớn nguồn có số domain duy nhất gần bằng số bản ghi. Riêng openphish có 296 URL trên 250 domain duy nhất; bitly.cx xuất hiện 15 lần. Không phát hiện cùng giá trị domain ở nhiều split, nhưng kiểm tra hiện tại chỉ dựa trên cột domain có sẵn.
3.4. Thiếu metadata thời gian và trạng thái
Trường	Có giá trị đọc được	Thiếu/không hợp lệ
collected_at	4.613 (8,68%)	48.503 (91,32%)
scraped_at	10.788 (20,31%)	42.328 (79,69%)
status	2.587 (4,87%)	50.529 (95,13%)


Mức thiếu collected_at không đồng đều theo nguồn: tinnhiem_org và tinnhiemmang có đủ giá trị; chongluadao thiếu 49,6%; openphish, tinnhiem_web, tranco và tranco_vn thiếu 100%. collected_at và scraped_at biểu thị hai thời điểm khác nhau, không nên dùng thay thế cho nhau.

Thông tin provenance khác: label_source có 33.823 bản ghi community và 19.293 feed; tier gồm 34.119 bronze, 9.593 gold và 9.404 silver.
4. Kết luận Data Reliability Gate
Đánh giá: Đạt một số kiểm tra cấu trúc cơ bản, nhưng chưa đủ cơ sở để kết luận toàn bộ dữ liệu đã vượt reliability gate. Không phát hiện trùng ID/URL, nhãn mâu thuẫn theo các khóa đã kiểm tra, URL thiếu hostname hoặc domain overlap theo cột domain. Ngược lại, source-label confounding rất mạnh, cơ cấu nguồn giữa các split khác nhau và metadata thời gian thiếu nhiều.
5. Việc cần làm tiếp
1. Khi đánh giá mô hình, báo cáo metric tổng thể và metric theo từng nguồn; nêu rõ hạn chế source-label confounding.
2. Nếu có đủ thông tin, kiểm tra tiếp registrable domain/campaign và các hạ tầng dùng chung trước khi kết luận về leakage.
3. Xây dựng external evaluation pilot có cả hai nhãn từ nhiều nguồn, bằng chứng nhãn và thời gian thu thập rõ ràng; giữ riêng khỏi train/validation/test.
4. Kiểm tra quyền sử dụng/điều khoản nguồn trước khi đưa dữ liệu external vào Git. Không đưa dữ liệu thô lên repository nếu chính sách hoặc giấy phép không cho phép.
Giới hạn: Audit này dựa trên metadata trong dataset_url.csv; không truy cập website, không xác minh độc lập nội dung/nhãn từng URL và không chứng minh loại bỏ mọi dạng campaign leakage.