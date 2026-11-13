# Benchmark

Bộ câu hỏi, split, gold và evidence nằm ở [`../data/benchmark.json`](../data/benchmark.json) (20 câu: 15 dev / 5 test, 5 câu có filter `ip_type`).

- Kiểm chứng evidence nguyên văn trên trang gold và filter khớp metadata: `python scripts/verify_benchmark.py` (cần `data/raw/introduction-intellectual-property.pdf`, xem README gốc).
- Chia dev/test và quy tắc độ khó: trường `split_policy`, `difficulty_scale` trong chính file JSON.
- Test (q16–q20) đã chạy **một lần** sau khi chốt cấu hình; không dùng để tinh chỉnh (`starter/results/exp3/FROZEN.md`).
- Tập **holdout** (10 câu, trang gold không trùng dev/test) cho phần mở rộng hybrid: [`../data/benchmark_holdout.json`](../data/benchmark_holdout.json); soạn và kiểm chứng trước khi chạy hybrid (`starter/results/hybrid/PROTOCOL.md`).
