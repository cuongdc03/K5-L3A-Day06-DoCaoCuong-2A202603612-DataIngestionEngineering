# Báo cáo cá nhân — Day 6: Data Ingestion Engineering

**Học viên:** Đỗ Cao Cường · **MSSV:** 2A202603612 · **Ngày chạy:** 2026-11-13 (UTC)
**Tóm tắt một dòng:** trên corpus *Introduction to Intellectual Property* (146 trang hữu ích), chunk theo cấu trúc (B2) cho chunk mạch lạc hơn hẳn chunk cố định 500 ký tự (coherence 1,90 so với 0,90 /2), và thêm filter `ip_type` (C2) cho kết quả truy xuất tốt nhất ở mẫu này, nhưng test chỉ có 5 câu nên **không kết luận chiến lược nào tốt nhất tổng quát**.

## Dữ liệu và pipeline

- **Chủ đề, nguồn/quyền:** OpenStax, *Introduction to Intellectual Property* (bản PDF, 201 trang vật lý, 5 chương: Patent Basics, Patent Enforcement, Copyright Basics, Trademark Basics, Trade Secret Basics). Giấy phép **CC BY** (OpenStax). URL, SHA-256 (`1498509864d37cb6…b378a`) và thời điểm truy cập `2026-11-13T07:17:20Z` nằm trong `data/manifest.json`. File PDF 24 MB không đưa vào repo (`data/raw/` bị ignore); cách lấy lại ở README.
- **Số trang và quy tắc tính:** **146 trang hữu ích, 431.109 ký tự** (chương 1: 42, chương 2: 31, chương 3: 33, chương 4: 24, chương 5: 16). Quy tắc cố định trước khi chạy: trang nằm trong thân 5 chương và có ≥ 700 ký tự chuẩn hóa. Loại: trang 1–16 (bìa, lời nói đầu, mục lục), 4 trang mở chương chỉ có hình + mục lục, phần Assessment Questions, glossary, answer key, index (9 trang trong chương bị loại, liệt kê ở `excluded_pages_inside_chapters`).
- **Chuẩn hóa, lỗi và giới hạn:** Unicode NFC, bỏ chân trang "Access for free at openstax.org", gộp khoảng trắng. Đọc PDF bằng PyMuPDF 2.1; `page_errors` = rỗng (146/146 trang đọc được, số ký tự khớp manifest). Không có trang scan nên không cần OCR. Giới hạn: header chạy chiếm 1,0% ký tự (4.321/431.109) ở 145/146 trang; chú thích cuối trang và chú thích hình lẫn trong văn bản; công thức/hình không có.
- **Embedding:** Google **EmbeddingGemma 2** chạy **local** qua sentence-transformers 6.3.0 (transformers 5.22.2, torch 2.15.0, thiết bị `mps`), **768 chiều**, vector chuẩn hóa. Tài liệu dùng prefix `title: none | text: `, truy vấn dùng `task: search result | query: ` (lấy từ `config_sentence_transformers.json` của model). `max_seq_length` = 512; không chunk nào vượt (token lớn nhất 421). Cùng model và prefix cho mọi cấu hình. Chi phí: **0 USD** (không dùng API).
- **Vector store:** PostgreSQL 16.16 + **pgvector 0.8.7** (Docker `pgvector/pgvector:0.8.7-pg16`, cổng 55433, volume bền vững), metric cosine, **tìm kiếm chính xác** (không tạo chỉ mục ANN). Bảng `chunks(strategy, chunk_id, …, embedding vector(768))`, khóa chính `(strategy, chunk_id)`.
- **Metadata:** bắt buộc `document_id`, `source`, `page` (trang PDF) cộng `printed_page`. Trường lọc bổ sung: **`ip_type`** (patent | copyright | trademark | trade_secret, kiểu text), cùng `chapter` (int), `section` (mục bắt đầu trước/tại trang, text) và `kind` (body | footnote). Giá trị `ip_type`/`chapter` lấy từ cấu trúc chương của sách (mục lục PDF), không tự đoán; chương 1–2 đều là patent. Lý do chọn `ip_type`: câu hỏi về cùng một khái niệm (fair use, injunction, thời hạn bảo hộ, đăng ký) xuất hiện ở nhiều chương với quy tắc khác nhau.
- **Nạp lại và tài liệu đổi:** `chunk_id` ổn định theo trang và vị trí; so `content_hash` để chỉ embed chunk mới/đổi; `prune` xóa chunk không còn được sinh ra. Đã kiểm chứng: nạp lại cùng phiên bản → 0 chunk embed, 1.016 và 645 dòng không đổi, không nhân đôi; giả lập 1 chunk đổi nội dung + 1 chunk mồ côi → embed lại đúng 1, xóa đúng 1, tái dùng 644.

## Cấu hình và benchmark

**Ba cấu hình chính** (cùng corpus, model, metric, benchmark; số liệu đầy đủ kèm đối chứng ở dưới):

| Cấu hình | Chunk | Metadata / truy xuất |
|---|---|---|
| **A** | Cửa sổ cố định 500 ký tự, chồng 50, theo từng trang, trên văn bản gốc (còn header) | Gắn nguồn và trang; không lọc |
| **B2** | Theo heading/đoạn dựa trên bố cục PDF (cỡ chữ), tối đa 1.200 ký tự, không vượt trang; bỏ header chạy; chú thích cuối trang thành chunk riêng; bỏ chunk < 30 ký tự | Cùng metadata; không lọc |
| **C2** | Giống hệt B2 (dùng lại chunk và vector) | Thêm lọc `ip_type` (khớp đúng) **chỉ ở câu hỏi có filter**; câu khác chạy không lọc |

**So sánh mỗi bước chỉ đổi một yếu tố** (đối chứng A2, B, C chạy cùng điều kiện):

| Bước | Yếu tố đổi |
|---|---|
| A → A2 | Chỉ bỏ header/số trang chạy (làm sạch) |
| A2 → B | Chỉ đổi cách chunk (cố định → theo cấu trúc) |
| B → B2 | Chỉ bỏ chunk < 30 ký tự |
| B2 → C2 (và B → C) | Chỉ thêm filter `ip_type` |

Ghi chú trung thực: A so với B2 trực tiếp lẫn ba yếu tố (header, cách chunk, mẩu vụn), nên tác động của chunking phải đọc ở bước A2 → B, và A → A2, B → B2 cho thấy hai yếu tố còn lại không đổi số liệu.

- **Benchmark:** `data/benchmark.json`, **20 câu** = **15 dev / 5 test**, chia theo quy tắc phân tầng độ khó và loại câu, **chốt trước khi chạy truy xuất** (q16–q20 là test: 1 dễ, 2 trung bình, 2 khó, trong đó 2 câu có filter). Độ khó chung: 4 dễ, 7 trung bình, 9 khó; loại câu: 4 trực tiếp, 4 diễn đạt lại, 7 điều kiện/ngoại lệ, 5 có filter (3 dev, 2 test). Mỗi câu có `expected_answer`, `gold_page(s)` và `evidence_quote`. **Kiểm chứng evidence:** `scripts/verify_benchmark.py` xác nhận cả 20 đoạn evidence nằm nguyên văn trên trang gold sau chuẩn hóa và mọi filter khớp metadata của trang gold (kết quả `PASS`). Filter là **input giả định được cung cấp trước** (người dùng đang đọc một chương/loại IP); câu hỏi không nêu tên nguồn hay trang. Nguy cơ rò rỉ được ghi từng câu trong `leakage_risk` (vd. q18 test cùng trang 116 với q01 và q13 dev).
- **Cách xây dựng câu hỏi:** Claude Code gợi ý câu hỏi từ nội dung các trang đã đọc; sau khi trao đổi với tác giả, hai bên thống nhất các câu hỏi và hướng benchmark (phân tầng độ khó, câu có filter, chia dev/test), rồi evidence được kiểm bằng script.
- **Tiêu chí chọn chiến lược (chốt trước khi xem test, `starter/results/exp3/FROZEN.md`, 07:47:51Z, trước lần chạy test 07:47:55Z):** Evidence Hit@3 trên dev cao nhất; hòa thì Hit@1 trên dev; hòa tiếp thì ít chunk/tài nguyên hơn. Kết quả: **C2**.

## Kết quả

Hit tự động rất chặt: chunk phải ở trang gold và chứa **trọn** đoạn evidence, evidence bị tách qua hai chunk được tính là trượt; bằng chứng tương đương ở trang khác không được tính (nên là cận dưới).

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian nạp | Chi phí |
|---|---|---|---|---|---|---|
| A | dev | 6/15 | 10/15 | 1.016 (474.609 ký tự, 104.614 token) | 33,3 s | 0 |
| A | test | 2/5 | 4/5 | | | |
| A2 (đối chứng) | dev | 6/15 | 10/15 | 1.008 (469.743 ký tự) | 32,5 s | 0 |
| A2 | test | 2/5 | 4/5 | | | |
| B (đối chứng) | dev | 8/15 | 11/15 | 640 (426.149 ký tự, 92.010 token) | ≈30,3 s (nạp đầy lần đầu, 645 chunk) | 0 |
| B | test | 3/5 | 5/5 | | | |
| **B2** | dev | 8/15 | 11/15 | 632 (425.981 ký tự, 91.913 token) | 31,5 s | 0 |
| **B2** | test | 3/5 | 5/5 | | | |
| C (đối chứng) | dev | 8/15 | 12/15 | 640 (dùng chung B) | 0 thêm | 0 |
| C | test | 4/5 | 5/5 | | | |
| **C2** (chọn) | dev | 8/15 | 12/15 | 632 (dùng chung B2) | 0 thêm | 0 |
| **C2** | test | 4/5 | 5/5 | | | |

Độ trễ truy vấn trung bình: embed truy vấn ≈ 43 ms (dev) và 54 ms (test); tìm kiếm pgvector 3–9 ms (exact scan, 632–1.016 dòng); đo một lần trên máy cục bộ (Apple MPS), chỉ mang tính tham khảo. Gộp 20 câu (chỉ mô tả, vì dev đã dùng để thiết kế): Hit@1 A 8/20, B2 11/20, C2 12/20; Hit@3 A 14/20, B2 16/20, C2 17/20.

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| A | **0,90** (10) — phân bố 0/1/2 = 1/9/0 | 15/15 | N/A (không lọc) | 0/0/5 → 2,00 |
| B2 | **1,90** (10) — 0/1/9 | 15/15 | N/A (không lọc) | 0/0/5 → 2,00 |
| C2 | 1,90 (cùng chunk với B2, chấm một lần) | 15/15 | **2/2** (q19, q20); dev 3/3 | 0/0/5 → 2,00 |

**Nơi lưu minh chứng:** trace top-3 đầy đủ (câu hỏi, ID và text chunk, score, metadata, nhãn evidence) tại `starter/results/exp3/traces_dev.jsonl` (dev, sáu cấu hình), `starter/results/final/traces_test.jsonl` (test, chạy **một lần**), tóm tắt `summary_*.json`, log nạp `starter/results/ingest_log.json`; snapshot thí nghiệm `exp1/`, `exp2/`, `exp3/`, `final/`. Nhãn thủ công: `starter/results/manual/` (`coherence_sheet.csv`, `metadata_sheet.csv`, `grounding_sheet.csv`).
**Cách chọn mẫu và chấm:**
- **Coherence:** 10 trang cách đều trong danh sách 146 trang (chỉ số 0, 15, …, 135 = trang PDF 18, 33, 48, 69, 84, 104, 119, 134, 155, 177); mốc là câu ở giữa trang (80 ký tự); chấm chunk chứa mốc, thứ tự xáo ngẫu nhiên có seed và **ẩn tên chiến lược**. Quy tắc cố định trước khi chấm (`coherence_positions.json`).
- **Metadata và grounding:** 5 câu test × top-3 × {A, B2, C2} (45 bản ghi; 15 tập top-3).
- **Người chấm:** coherence mục 1–5 do tác giả chấm. Phần còn lại (coherence mục 6–20, metadata, grounding) do **Claude đề xuất** (đối chiếu từng bản ghi với PDF và đọc cả top-3); **tác giả đã xem và chấp nhận nguyên văn, không sửa nhãn nào**. Cột `label_source` trong từng file ghi rõ điều này.

## Phân tích và kết luận

**Retrieval (tiêu chí 1).** C2 cao nhất ở cả dev (Hit@3 12/15) và test (Hit@1 4/5, Hit@3 5/5), nhưng mỗi câu test = 20 điểm %, mỗi câu dev = 6,7 điểm %, nên chênh 1–2 câu không đủ để kết luận. Theo độ khó (gộp 20 câu, Hit@3): dễ A 3/4, B2 4/4, C2 4/4; trung bình A 5/7, B2 6/7, C2 7/7; khó cả ba đều 6/9.

**A–B (chunking, tiêu chí 5).** Làm sạch header (A→A2) **không đổi** số liệu nào: Hit@1/Hit@3 dev 6/15 và 10/15, test 2/5 và 4/5 giữ nguyên, điểm top-1 lệch tối đa 0,0004, dù ranh giới cửa sổ đổi nên top-3 của 7/15 câu dev khác chunk và số chunk top-3 chứa header giảm từ 6/45 xuống 0/45. Đổi cách chunk (A2→B) tăng Hit@1 dev 6→8/15 và Hit@3 10→11/15, test 2→3/5 và 4→5/5, với ít chunk hơn (640 so với 1.008) và ít token hơn (92.010 so với 102.853), thời gian nạp tương đương. Bỏ mẩu vụn < 30 ký tự (B→B2) chỉ đổi top-3 của q10 và **không đổi** metric nào.

**B–C (filter).** B2→C2 chỉ khác ở các câu có filter (q13–q15 dev, q19–q20 test) và **không tốn thêm** lưu trữ hay embedding. Nó giúp q14 (dev: Hit@3 từ trượt sang đúng, chunk trademark thay chunk copyright fair use) và q20 (test: Hit@1 từ trượt sang đúng, vì B2 xếp hai chunk bí mật thương mại lên trước chunk patent). Với q13, q15, q19 filter không đổi kết quả. Tuân thủ filter 5/5 câu (dev 3/3, test 2/2).

**Coherence (tiêu chí 2).** B2 1,90 /2 so với A 0,90 /2: chunk cố định 500 ký tự bị cắt giữa từ/giữa ý ở hầu hết vị trí (9/10 điểm 1, một điểm 0 ở trang 155 khi mất heading và cắt danh sách 5 yếu tố). B2 chỉ mất điểm ở vị trí trang 48 vì chunk **không vượt trang**: đoạn tiếp nối từ trang trước mất chủ thể ("the Founding Fathers specifically designed the patent system to…"). Mẫu 10 vị trí mỗi nhóm, tác giả chấm 3 (A) và 2 (B2/C2) trong số đó.

**Metadata (tiêu chí 3).** 45/45 bản ghi đủ và đúng (kiểm tra với PDF: chunk nằm đúng trang, số trang in khớp con số trên header, chương/`ip_type` khớp mục lục). Trường giúp ích rõ nhất: `ip_type` (lọc, q14 và q20) và `page`/`printed_page` (truy vết về đúng trang sách). Hạn chế: metadata gắn theo **trang**, không theo chunk, nên 45/45 chủ yếu phản ánh pipeline gắn đúng, ít phân biệt được chiến lược; `section` chỉ là mục bắt đầu trước/tại trang, một trang có thể chứa nhiều mục; `ip_type` suy từ cấu trúc chương, không bắt được đoạn lạc đề; chương 1 và 2 đều là patent nên `ip_type` không tách được hai chương.

**Grounding (tiêu chí 4).** Cả ba cấu hình đạt 15/15 mức 2 (trung bình 2,00) trên 5 câu test, vì top-3 luôn có đủ bằng chứng. Thang này **bão hòa** ở mẫu nhỏ và không phân biệt được các cấu hình; khác biệt chỉ nằm ở thứ tự và nhiễu (q20: B2 đặt hai chunk bí mật thương mại lên hạng 1–2, chunk đúng ở hạng 3). Grounding chỉ đo độ đủ bằng chứng truy xuất, **không** phải độ chính xác câu trả lời LLM. Có khác biệt với Hit@3 tự động: q16 của A có Hit@3 bằng 0 nhưng grounding 2, vì chunk hạng 1 ở trang 66 nói đúng USPTO cấp bằng.

**Hai ví dụ sai.**
1. **q10 (dev, khó, `openstax-intro-ip` trang 153):** "Can a word that merely describes a quality of the product be registered as a trademark?" B/B2/C/C2 đều trượt Hit@3. Chunk chứa trọn evidence (heading *Descriptive Marks*) đứng **hạng 4** (đo trên B2, khi lọc 632 chunk), trong top-3 của B có chunk 18 ký tự `Trademark Basics 4` (header sót, B) rồi chunk trang 147 (B2), tức nhiễu ngắn đẩy chunk đúng ra ngoài. Bỏ mẩu vụn (B2) không cứu được: vẫn một chunk sai khác thế chỗ. Lỗi nằm ở xếp hạng, không ở nhiễu hay mất evidence.
2. **q16 (test, dễ, trang 19):** "Which U.S. government agency issues patents?" Hit@1 trượt ở A, B2 và C2: hạng 1 là chunk mở đầu chương 2 (trang 66, *Introduction 2.1 The Right to Enforce Patents…*), chunk gold (`B2-p019-00`) ở hạng 3; A trượt cả Hit@3 theo định nghĩa chặt vì cửa sổ 500 ký tự cắt rời câu định nghĩa, dù chunk hạng 1 ở trang 66 vẫn nói USPTO cấp bằng (equivalent evidence).

**Chiến lược chọn và điều kiện áp dụng.** **C2**, theo tiêu chí đã chốt. Đánh đổi: ít chunk và coherence cao (B2), filter không tốn tài nguyên nhưng chỉ dùng được khi ngữ cảnh người dùng cung cấp trước `ip_type`; không có filter thì C2 = B2. Chỉ áp dụng cho corpus này (sách giáo trình tiếng Anh có cấu trúc rõ, font phân biệt heading), không suy rộng.

**Hạn chế.**
- **Test và dev nhỏ:** 5 câu test, 15 câu dev; chênh 1 câu bằng 20 điểm % (test) hoặc 6,7 điểm % (dev). Test chạy một lần sau khi chốt cấu hình; **không dùng điểm test để tinh chỉnh**.
- **Thí nghiệm sau khi xem dev:** A2 (exp2) và B2/C2 (exp3) được thêm sau khi xem kết quả dev, ghi trong `artifacts/experiment_log.csv`. Trước mọi lần truy xuất, tôi đã gộp tiêu đề liên tiếp và mẩu < 80 ký tự trong B (645 → 640 chunk).
- **Rò rỉ trang:** test q18 trùng trang 116 với dev q01 và q13; q20 kề q11 (trang 90).
- **Nhãn:** phần lớn nhãn thủ công do Claude đề xuất rồi tác giả chấp nhận; có nguy cơ thiên lệch và thiếu độc lập (người chấm cũng là người thiết kế benchmark, đã thấy số Hit). Chỉ 5/20 nhãn coherence là điểm tác giả tự chấm.
- **Câu hỏi:** do Claude gợi ý và chốt sau khi trao đổi với tác giả, không phải tác giả tự viết hoàn toàn; benchmark bằng tiếng Anh, chưa thử truy vấn tiếng Việt.
- **Hit tự động chặt:** coi evidence tách chunk là trượt, không công nhận bằng chứng tương đương ở trang khác.
- **Đo thời gian/chi phí:** một lần chạy trên một máy, không lặp; chi phí 0 vì model local.
- **Dữ liệu:** nhiễu header chỉ 1% nên cleaning khó thấy tác động.

**Nếu làm lại hoặc mở rộng.**
1. Tạo tập test mới lớn hơn và độc lập (không cùng trang với dev), có nhãn do nhiều người chấm.
2. Hybrid BM25 + dense: các câu trượt sát nút (q09 hạng 5, q10 hạng 4, q13 hạng 4) đều có từ khóa rõ.
3. Cho phép chunk vượt ranh giới trang (nối đoạn tiếp nối) để sửa lỗi coherence ở đầu trang.
4. Thử embedding khác (OpenRouter/OpenAI) và truy vấn tiếng Việt.

## AI/công cụ đã dùng và cách kiểm tra
Claude Code (mô hình Sonnet 5.5) dùng để viết mã pipeline, gợi ý câu hỏi benchmark (chốt cùng tác giả), đề xuất nhãn thủ công và nháp báo cáo. Cách kiểm tra: `scripts/verify_benchmark.py` (evidence nguyên văn trên trang gold, filter khớp metadata), đối chiếu số trang in với header PDF, kiểm tra nạp lại và tài liệu đổi bằng lệnh thật, chạy lại A/B/C cho kết quả trùng khớp exp1; các lỗi trong lúc làm đã sửa và ghi lại (pip treo → dùng `uv`; psycopg không autocommit làm lần nạp đầu bị rollback, đã xóa log sai và nạp lại; cảnh báo section giả do regex nhầm chú thích hình/bảng đã gỡ khỏi nhãn). Corpus: OpenStax, CC BY; trích dẫn trong trace thuộc nội dung đó.
