# Bảng chấm thủ công

Ba file CSV (UTF-8 có BOM, mở được bằng Excel/Numbers/Google Sheets). **Mọi cột có chữ `(FILL)` là nhãn do người chấm điền; đang để trống.** Cột `auto_*` chỉ là kiểm tra cơ học để đối chiếu nhanh, không phải nhãn.

Người chấm: tác giả bài lab. Nguy cơ thiên lệch: người chấm cũng là người thiết kế benchmark và đã thấy số Hit tự động. Để giảm: chấm `coherence_sheet.csv` trước (không phụ thuộc kết quả truy xuất), ẩn cột `auto_hint` khi chấm grounding, và chấm theo từng câu hỏi chứ không theo từng chiến lược.

## 1. `coherence_sheet.csv` (20 dòng = 10 vị trí × {A, B2/C2})
Quy tắc chọn vị trí (cố định trước khi chấm, xem `coherence_positions.json`): 10 trang đếm được cách đều (chỉ số 0, 15, …, 135), mỗi trang lấy câu ở giữa trang làm mốc; mỗi chiến lược được chấm trên chunk chứa mốc đó. C2 dùng đúng chunk của B2 nên chấm một lần.

Thang điểm cho `chunk_text`:
- **0** = bị cắt giữa ý / thiếu chủ thể làm không hiểu.
- **1** = hiểu một phần, thiếu ngữ cảnh.
- **2** = tự hiểu được và giữ trọn ý.

Ghi lý do ngắn ở cột `reason`. Điểm trung bình /2 tính cho từng chiến lược.

## 2. `metadata_sheet.csv` (45 dòng = 5 câu test × top-3 × {A, B2, C2})
Đối chiếu từng dòng với trang PDF `page` (số trang in `printed_page` = trang PDF − 8; `ip_type` suy từ chương của sách). Điền y/n, một bản ghi chỉ tính "đủ và đúng" khi source, page và ip_type đều đúng. Ghi từng lỗi ở `error_note`.
- Câu có filter (q19, q20): báo số câu mà top-3 tuân thủ filter / số câu có filter (cột `auto_filter_satisfied` gợi ý).
- Cần giải thích: ít nhất một trường giúp truy vết hoặc lọc, và một hạn chế (ví dụ `section_at_page_start` chỉ là mục bắt đầu trước trang, không phải mục chứa chunk).

## 3. `grounding_sheet.csv` (15 dòng = 5 câu test × {A, B2, C2}, mỗi dòng 3 chunk)
Chỉ đánh giá **bằng chứng truy xuất**, không phải độ chính xác câu trả lời LLM. Cho điểm top-3 như một tập:
- **0** = không có bằng chứng.
- **1** = có nhưng thiếu điều kiện / ngữ cảnh cần thiết.
- **2** = đủ để trả lời và truy nguồn.

Báo số lượng từng mức và trung bình /2 kèm lý do. Evidence Hit@3 tự động không thay nhãn này.

Lưu ý: test đã được xem một lần ở bước truy xuất. Không dùng nhãn thủ công để chỉnh lại tham số; nếu muốn thí nghiệm tiếp, tạo tập test mới.

## Trạng thái nhãn (cập nhật)
- `coherence_labels_final.csv`: mục 1-5 do **tác giả** chấm; mục 6-20 do **Claude đề xuất** (chấm mù tên chiến lược), cần tác giả rà soát và sửa. Mục 6 chưa được tác giả chấm.
- `metadata_sheet_labeled_llm.csv`, `grounding_sheet_labeled_llm.csv`: nhãn **Claude đề xuất**, có đối chiếu với PDF; chưa phải nhãn của tác giả cho đến khi được rà soát.
- Phương pháp ghi trong báo cáo: LLM hỗ trợ chấm, tác giả xem xét và sửa; nêu rõ nhãn nào bị sửa.
