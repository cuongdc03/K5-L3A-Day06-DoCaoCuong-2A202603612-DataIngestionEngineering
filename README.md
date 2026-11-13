# Day 06 · Data Ingestion Engineering

## Bài làm cá nhân — cách chạy lại

**Đề tài:** OpenStax *Introduction to Intellectual Property* (CC BY), 146 trang hữu ích. Pipeline: PyMuPDF → chunk (A cố định, B2 theo cấu trúc, C2 = B2 + filter `ip_type`) → EmbeddingGemma 2 local (768 chiều) → PostgreSQL 16 + pgvector 0.8.7. Báo cáo: [report/individual/2A202603612_DoCaoCuong.md](report/individual/2A202603612_DoCaoCuong.md).

```bash
# 1. Dữ liệu (không commit PDF; kiểm SHA-256 theo data/manifest.json)
mkdir -p data/raw
curl -L -o data/raw/introduction-intellectual-property.pdf \
  https://assets.openstax.org/oscms-prodcms/media/documents/introduction-intellectual-property_-_WEB.pdf
shasum -a 256 data/raw/introduction-intellectual-property.pdf   # 1498509864d37cb63a6ccc11bab7c783f3d30b2ed37d808ef80c56fdb676378a

# 2. Môi trường (Python 3.11–3.14) và database
cd starter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # nếu pip treo, dùng: uv pip install -r requirements.txt
cp .env.example .env                     # DATABASE_URL local; không cần API key
docker compose -p day6_student_starter up -d --wait
python scripts/check_setup.py            # kỳ vọng: pgvector 0.8.7, "Setup OK"

# 3. Model embedding local: đặt vào starter/models/google/embeddinggemma-2/
#    (Google EmbeddingGemma 2, Apache-2.0; thư mục models/ bị .gitignore vì nặng 1,4 GB)

# 4. Manifest và benchmark (từ thư mục gốc repo)
cd .. && python scripts/build_manifest.py          # tạo data/manifest.json
python scripts/verify_benchmark.py                 # kỳ vọng: PASS

# 5. Nạp, đánh giá (từ starter/)
cd starter
python -m src.run ingest                           # ~70 s lần đầu; chạy lại không nhân đôi
python -m src.run eval --split dev --tag exp3      # sáu cấu hình A, A2, B, B2, C, C2
python -m src.run eval --split test --final --tag final   # test bị khóa; chỉ chạy sau khi chốt cấu hình
python scripts/make_manual_sheets.py               # sinh bảng chấm thủ công (nhãn không được điền tự động)
```

Kết quả và minh chứng: `starter/results/{exp1,exp2,exp3,final}/` (trace top-3, summary), `starter/results/ingest_log.json` (thời gian, chunk, phiên bản), `starter/results/manual/` (nhãn thủ công), `artifacts/experiment_log.csv`. Seed duy nhất: thứ tự chấm coherence (`20261113`). Chi phí embedding 0 USD (local). Kết quả có thể lệch nhẹ ở chữ số thập phân trên máy/thiết bị khác (MPS so với CPU).

---

**Lab cá nhân** · **4 giờ** · **Dữ liệu tự chọn**

Biến tài liệu thành kho tri thức có thể truy xuất cho AI agent, rồi đo xem cách chuẩn bị dữ liệu nào hiệu quả nhất.

| 📄 Dữ liệu | 🧩 Chiến lược | 🎯 Benchmark |
|---|---|---|
| Tối thiểu **30 trang nội dung** | Tối thiểu **3 cấu hình** | Tối thiểu **20 câu hỏi** |

## Bắt đầu nhanh

Dùng [starter PostgreSQL + pgvector](starter/README.md) để dựng database và hoàn thiện các hàm TODO, hoặc tự chọn vector store tương đương. Starter chỉ là khung: **bạn tự hiện thực pipeline và benchmark**.

## 1. Xây pipeline

![Đọc tài liệu, chuẩn hóa, chia chunk, tạo vector, lưu và kiểm tra](assets/ingestion-pipeline.svg)

Chọn tài liệu được phép sử dụng; giữ **ID tài liệu, nguồn, trang/vị trí** và metadata phù hợp. Dùng embedding model thật qua API hoặc chạy local; lưu và truy xuất bằng pgvector, Qdrant, Chroma hoặc một store tương đương.

## 2. So sánh và đánh giá

![Ba chiến lược được đánh giá trên cùng corpus và benchmark dev/test](assets/benchmark-workflow.svg)

Dùng cùng dữ liệu, model và câu hỏi cho cả ba cấu hình. Tách **15 câu dev / 5 câu test** trước khi chạy; chọn cấu hình trên dev, rồi đánh giá test sau khi cố định. Mỗi câu hỏi cần có đoạn bằng chứng và trang nguồn; thiết kế bộ câu hỏi và đánh giá theo [BENCHMARK.md](BENCHMARK.md).

Đánh giá theo năm khía cạnh: **độ chính xác truy xuất**, **tính mạch lạc của chunk**, **tính hữu dụng của metadata**, **chất lượng grounding** và **tác động của chiến lược dữ liệu**. Giải thích lựa chọn bằng kết quả, ví dụ lỗi và các đánh đổi.

## 3. Chuẩn bị bài nộp

1. Chạy pipeline và lưu cấu hình, kết quả top-3, trace cùng nhãn đánh giá thủ công.
2. Điền [thông tin học viên](STUDENT.md), [nhật ký thí nghiệm](artifacts/experiment_log.csv) và bản sao [mẫu báo cáo cá nhân](report/individual/MSSV_HoTen.md).
3. Kiểm tra mã nguồn, cách chạy, manifest dữ liệu và checklist trong [SUBMISSION.md](SUBMISSION.md).

## Tài liệu hướng dẫn

| Bạn cần tìm | Tài liệu |
|---|---|
| Setup baseline PostgreSQL + pgvector | [starter/README.md](starter/README.md) |
| Các bước làm và cách tính chỉ số | [GUIDE.md](GUIDE.md) |
| Tiến độ trong 4 giờ | [CHECKPOINTS.md](CHECKPOINTS.md) |
| Năm tiêu chí benchmark và bộ câu hỏi | [BENCHMARK.md](BENCHMARK.md) |
| Tiêu chí chấm điểm | [RUBRIC.md](RUBRIC.md) |
| Quy tắc sử dụng dữ liệu, AI và API | [RULES.md](RULES.md) |
| Cách nộp bài | [SUBMISSION.md](SUBMISSION.md) |

[data/format-example.json](data/format-example.json) chỉ minh họa định dạng, không phải corpus đủ điều kiện. Phần xử lý và benchmark do bạn tự hiện thực; không bắt buộc xây chatbot.
