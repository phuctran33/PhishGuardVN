# Kiểm chứng ML tuần 5

Kiểm tra 04/11/2026: **152 tests passed, 0 skipped**, `pip check` không có lỗi dependencies.
Lần train gốc của notebook E2 ablation đã thực thi đủ 12 code cells, không có error output. Sau đó chỉ đổi cell export sang CSV nén, không train lại. Notebook 05 và kết quả/model E1 cũ giữ nguyên checksum.

- Chạy code Hy `05_build_matrix_x_brand.py --partition trainval`: 14.663 dòng (13.078 Train, 1.585 Validation), 2 exclusions; 12 lexical và IDs khớp E1.
- Recompute độc lập từ **130.780 OOF** và **15.850 Validation predictions**: 30 CV metric rows và 10 Validation metric rows khớp AP/P/R/F1/FPR/confusion.
- OOF mỗi candidate/ID đúng một dòng, nhãn/fold khớp metadata gốc; không có Validation/Test trong fitting partitions; outer/inner domains disjoint.
- Kết quả E1 trong notebook E2 ablation khớp metrics notebook 05 trong sai số 1e-10. Không ghi đè bảng/model baseline đã khóa.
- Ba CSV nén giải nén ra đúng nguyên byte của CSV lần chạy gốc; ID, score, labels và partitions giữ nguyên. Hash của ba file được ghi trong metadata. Code các cell khác save giữ nguyên; metadata bảo lưu hash notebook gốc lúc train và ghi hash notebook sau sửa export. Raw reference LF/CRLF được ghi trong metadata; không đổi nội dung reference.
- Kiểm thử notebook thật trên fixture: scaler/GridSearch chỉ fit đúng partition, thay nhãn Validation/Test không đổi OOF/shortlist;
  đổi đáp án outer held-out không đổi predictions fold đó; khác ID/lexical/schema hoặc Test lọt X/folds thì dừng.
- Reload E2 có cùng score/label với extractor trực tiếp, dùng reference snapshot; invalid URL/source formula drift bị từ chối.
- CLI predict Windows UTF-8 và SVM margin đã có regression test; hai feature-set bundles chạy bằng runner chung.

Kiểm tra cuối trước commit: tạo bản sao code hiện tại từ cloned base, không có model hay bảng E2 sẵn, chỉ có bốn handoff tuần 4 đã xác minh.
Chạy extractor Hy trainval → `scripts/train_week5.py --ablation` thực thi đủ **12 code cells** với tên `05_e2_ablation.ipynb` → CLI predict từ model mới.
**14 bảng** gồm OOF/Validation/partitions, tham số, metrics, delta, shortlist và lỗi tái lập trong sai số **1e-10**; cả ba CSV nén có checksum hợp lệ.
CLI E2 MLP probability, E2 SVM margin và E1 MLP đều pass. Cùng môi trường Python/thư viện; không coi đây là kiểm chứng xuyên phiên bản/hệ điều hành.

[Record kiểm tra](tables/06_verification.json). Đây là **producer verification**, không gán thay independent audit/human review của Hưng.
Không có đánh giá Test/ngoài dataset/mobile. Lần này không chạy lại từ raw data trên hệ điều hành hay phiên bản thư viện khác.

Kiểm chứng lịch sử: notebook 05 v2 đã có clean rerun cùng bốn handoffs khớp 1e-10,
chi tiết ở cuối [week5_readable.md](week5_readable.md). Các kiểm tra v1 ở [archive](archive/week5_nested_v1/week5_validation.md).
