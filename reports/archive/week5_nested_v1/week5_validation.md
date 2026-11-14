# Kiểm chứng mốc tuần 5: 12 feature — Phúc

Kết quả thuộc lần chạy có source manifest `e4999ae0a0555e6a0edf86f84b7d8cdc35a3505f5683172ec95d756ee67d1f5d`. Đây là mốc lexical-only trước khi Hy bàn giao brand features; chưa nghiệm thu toàn bộ tuần 5.

## Đã kiểm tra

- Toàn bộ suite trên môi trường local: **104 tests pass**, gồm 27 tests runner và 6 tests reporting mới. Cảnh báo còn lại là deprecation `registered_domain` của parser hiện tại.
- Notebook 05 chạy thành công ở chế độ đọc kết quả; CLI predict load model đã lưu và dùng lại parser/extractor.
- Bản sao sạch không có handoff/model: chạy notebook 01 → 03 → 02, sau đó `scripts/train_week5.py`. Dùng cùng Python/thư viện đã ghi trong metadata. Handoff SHA256 giống bản chính; CV summary và validation metrics khớp sai số tuyệt đối1e-10. Không tuyên bố tái lập qua mọi phiên bản thư viện.
- Tính lại độc lập metrics từ65.390 OOF predictions và7.925 validation predictions: khớp bảng đã lưu; không có official test ID trong predictions.
- Cả68 lần fit đã hội tụ; 67 split-audit rows không trùng domain giữa fitting/held-out. Kiểm chứng này không loại bỏ source bias.
- 26 file E1 trong snapshot vẫn nguyên byte: source/config/notebook04/reports04/model/metadata. Hai đối chứng LR có delta mean AP/F1 so với E1 bằng0 ở độ chính xác đã lưu.
- Source/config/input/artifact hash khớp metadata. Review độc lập không phát hiện lỗi P0/P1 trong luồng đã chạy.

## Cách đọc kết quả

Mean CV AP: LR0.5942; LRbalanced0.5577; SVM0.6426; MLP0.6992; HistGB0.6979. MLP cao nhất theo quy tắc AP đã chốt, nhưng chỉ hơn HistGB khoảng0.0013. Ba folds và dao động hiện tại chưa đủ cơ sở nói MLP vượt trội; đây là ứng viên tạm, không phải Teacher cuối.

MLP đạt mean CV F1≈0.5989/FPR≈2.32%; HistGB F1≈0.6066/FPR≈2.01%. LRbalanced E1 có recall cao hơn nhưng FPR≈28.94%. Các điểm ngưỡng0.5 khác nhau về trade-off; không kết luận một model tốt hơn ở mọi tiêu chí.

Official validation chỉ bổ sung: MLP AP≈0.4314, HistGB AP≈0.4338; cả hai vẫn có FP/FN đáng kể, validation có24positive. Không dùng các điểm này để đổi winner hoặc threshold. Xem report đầy đủ và metadata.

## Tài nguyên PC đã đo

Chạy `python scripts/benchmark_week5.py` sau train. Một thread,3warmups và20repetitions mỗi model/batch. Kích thước là serialize riêng mỗi estimator bằng joblib không nén; latency dưới đây là predict_proba của batch1 sau warmup, chưa gồm parsing/feature extraction/loading. Không phải số đo mobile hoặc RAM.

| Model | Model KiB | Median ms / batch1 | p95 ms / batch1 |
|---|---:|---:|---:|
| hist_gradient_boosting | 140.47 | 1.1221 | 1.6175 |
| logistic_regression | 2.08 | 0.5819 | 0.7058 |
| logistic_regression_balanced | 2.09 | 0.5837 | 0.6947 |
| mlp | 43.09 | 0.5891 | 0.7795 |
| svm_rbf | 570.59 | 1.3742 | 1.9328 |

Chi tiết/hash/sample/phiên bản ở tables/05_resource_metadata.json và05_resource_benchmark.csv. Số batch128 là thời gian cả batch, không gọi là latency một URL. Không chọn lại model theo benchmark này.

MLP hiện tại đã nhỏ; cần so sánh Student hard-only với Student KD và đo tài nguyên thực trước khi khẳng định chưng cất có ích. Không mặc định MLP/boosting top2 sẽ là Teacher.

## Bàn giao và còn chờ

- Hưng có thể tạo lại predictions bằng CLI để audit theo ID/source/tier/fold và kiểm tra robustness; Khiêm bổ sung bias/external evidence.
- Chờ Hy: feature dictionary/spec/version/hash, finite/error policy và X brand theo ID. Sau review mới mở schema và chạy đối chứng trên same eligible samples/folds.
- Chưa tune threshold, chưa brand ablation, chưa Teacher final, chưa Student/KD/mobile.
- Hạn chế kỹ thuật không chặn lần chạy thành công: khi toàn bộ cấu hình một family thất bại hoặc refit không hội tụ, runner sẽ dừng; fit/search logs khi đó còn trong bộ nhớ và chưa được ghi có cấu trúc. Nên bổ sung checkpoint/failure diagnostics ở vòng cải tiến sau. Lần chạy đã bàn giao không có fit thất bại.

## Cách chạy

```powershell
.\.venv\Scripts\python.exe scripts/train_week5.py
.\.venv\Scripts\python.exe scripts/benchmark_week5.py
.\.venv\Scripts\python.exe scripts/predict_week5.py https://example.com/a
```
