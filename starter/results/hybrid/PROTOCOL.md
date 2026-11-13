# Hybrid retrieval extension: protocol (written before any hybrid run)
Written at: 2026-11-13T08:13:20Z (UTC). No hybrid result existed at this time.

- Chunks, vectors, metadata and filter convention: exactly C2 (strategy B2). Only the retrieval step changes.
- Systems compared: dense (= C2 baseline), BM25 only, hybrid (dense + BM25, candidates = top 50 from each).
- BM25: Okapi, k1=1.5, b=0.75 (textbook defaults, not tuned), lowercase + stopwords + light suffix stripping; idf over all B2 chunks; filter applied after scoring.
- Tuned on the 15 DEV questions only: fusion method/weight in {RRF(k=60), weighted alpha 0.3/0.5/0.7/0.8}.
- Selection rule (fixed now): max Evidence Hit@3 on dev, then Hit@1, then RRF, then larger dense weight. 'dense' and 'bm25' are references, not selectable.
- Questions not used for tuning: (a) the 5 original TEST questions (q16-q20; seen once for the C2 choice, never for hybrid), (b) 10 new HOLDOUT questions (data/benchmark_holdout.json, sha256 below, gold pages disjoint from dev/test, evidence verified before any hybrid run).
- Report cases where hybrid is worse than dense, not only where it is better. Small-sample caveat applies (15 unseen questions).

data/benchmark_holdout.json sha256: 6eff42c5707f03ce4cc29705cf948a9f3b0e9683d8d21138d1dc16268bb66904
