"""Pipeline entry point (run from starter/):

    python -m src.run ingest              # read PDF -> chunk (A,B) -> embed -> pgvector; safe to re-run
    python -m src.run eval --split dev    # top-3 for strategies A, B, C on dev questions
    python -m src.run eval --split test --final   # only after strategy/params are frozen

C shares the chunks and vectors of B and only adds the metadata filter at query time.
Backend failures raise; nothing falls back to mock data.
"""
import argparse
from dataclasses import replace
import json
import os
import statistics
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

from . import config
from .chunking import by_paragraph, content_hash, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pages
from .store import PgVectorStore


def _store() -> PgVectorStore:
    load_dotenv(config.STARTER / ".env")
    store = PgVectorStore(os.environ["DATABASE_URL"], config.DIMENSIONS)
    store.create_schema()
    return store


def _versions() -> dict:
    import importlib.metadata as md
    return {p: md.version(p) for p in ("sentence-transformers", "transformers", "torch", "psycopg", "pymupdf")}


def build_chunks(pages) -> dict[str, list]:
    a, b = config.STRATEGIES["A"], config.STRATEGIES["B"]
    a2, b2 = config.STRATEGIES["A2"], config.STRATEGIES["B2"]
    return {"A": [c for p in pages for c in fixed_size(p, a["size"], a["overlap"])],
            "A2": [c for p in pages for c in fixed_size(_without_header(p), a2["size"], a2["overlap"], "A2")],
            "B": [c for p in pages for c in by_paragraph(p, b["max_size"])],
            "B2": [c for p in pages for c in by_paragraph(p, b2["max_size"], "B2", b2["drop_below"])]}


def _without_header(page):
    """Same page, text rebuilt from layout blocks minus the running header (title + page number)."""
    text = " ".join(b["text"] for b in page.metadata["blocks"] if b["kind"] != "header")
    return replace(page, text=text)


def _dist(values: list[int]) -> dict:
    s = sorted(values)
    return {"min": s[0], "p10": s[len(s) // 10], "median": statistics.median(s),
            "mean": round(statistics.mean(s), 1), "p90": s[int(len(s) * 0.9)], "max": s[-1]}


def cmd_ingest(_: argparse.Namespace) -> None:
    t_all = time.perf_counter()
    pages, errors = load_pages()
    t_read = time.perf_counter() - t_all
    embedder = MyEmbedder()
    store = _store()
    chunks_by = build_chunks(pages)
    log = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model": config.MODEL_NAME, "dimensions": config.DIMENSIONS, "device": embedder.device,
           "doc_prompt": config.DOC_PROMPT, "query_prompt": config.QUERY_PROMPT,
           "max_seq_length": config.MAX_SEQ_LENGTH, "versions": _versions(),
           "vector_store": "pgvector 0.8.7 / PostgreSQL 16, cosine, exact scan (no ANN index)",
           "cost_usd": 0.0, "pages": len(pages), "page_errors": errors,
           "read_seconds": round(t_read, 2), "strategies": {}}
    for name, chunks in chunks_by.items():
        t0 = time.perf_counter()
        old = store.existing_hashes(name)
        todo = [c for c in chunks if old.get(c.chunk_id) != content_hash(c.text)]
        vectors_new = embedder.embed_documents([c.text for c in todo]) if todo else []
        by_id = {c.chunk_id: v for c, v in zip(todo, vectors_new)}
        # unchanged chunks keep their stored vector; only new/changed chunks are (re-)embedded
        written = store.upsert(name, todo, vectors_new) if todo else 0
        deleted = store.prune(name, [c.chunk_id for c in chunks])
        tokens = embedder.token_counts([c.text for c in chunks])
        chars = [len(c.text) for c in chunks]
        log["strategies"][name] = {
            "params": config.STRATEGIES[name], "n_chunks": len(chunks), "n_rows_in_db": store.count(name),
            "re_embedded": len(by_id), "reused_from_db": len(chunks) - len(by_id), "written": written, "deleted_obsolete": deleted,
            "total_chars": sum(chars), "total_tokens": sum(tokens),
            "chars": _dist(chars), "tokens": _dist(tokens),
            "tokens_over_max_seq": sum(t > config.MAX_SEQ_LENGTH for t in tokens),
            "kinds": {k: sum(c.metadata["kind"] == k for c in chunks) for k in ("body", "footnote")},
            "ingest_seconds": round(time.perf_counter() - t0, 2)}
    log["total_seconds"] = round(time.perf_counter() - t_all, 2)
    config.RESULTS.mkdir(exist_ok=True)
    runs = []
    path = config.RESULTS / "ingest_log.json"
    if path.exists():
        runs = json.loads(path.read_text())
    runs.append(log)
    path.write_text(json.dumps(runs, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in log.items() if k != "versions"}, ensure_ascii=False, indent=1))


def cmd_eval(args: argparse.Namespace) -> None:
    if args.split == "test" and not args.final:
        raise SystemExit("test split is locked: freeze strategy/params first, then pass --final")
    bench = json.loads(config.BENCHMARK.read_text())["questions"]
    questions = [q for q in bench if q["split"] == args.split]
    embedder, store = MyEmbedder(), _store()
    for name, params in config.STRATEGIES.items():
        index = params.get("index_of", name)
        if store.count(index) == 0:
            raise SystemExit(f"strategy {index} has no rows: run `python -m src.run ingest` first")
    traces = []
    for q in questions:
        t0 = time.perf_counter()
        qv = embedder.embed_query(q["question"])
        t_embed = time.perf_counter() - t0
        for name, params in config.STRATEGIES.items():
            index = params.get("index_of", name)
            flt = q["filter"] if params["filter"] else None
            t1 = time.perf_counter()
            hits = store.search(index, qv, config.TOP_K, flt)
            tr = evaluate_query(q, hits)
            tr.update({"strategy": name, "index": index, "filter_used": flt,
                       "search_ms": round((time.perf_counter() - t1) * 1000, 1),
                       "embed_query_ms": round(t_embed * 1000, 1)})
            if flt:   # filter compliance: every hit must satisfy it
                tr["filter_ok"] = all(h.get(k) == v for h in hits for k, v in flt.items())
            traces.append(tr)
    summary = summarize(traces)
    out = config.RESULTS / args.tag
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (out / f"traces_{args.split}.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in traces) + "\n")
    (out / f"summary_{args.split}.json").write_text(
        json.dumps({"run_at": stamp, "split": args.split, "summary": summary}, indent=1))
    print(f"split={args.split}  questions={len(questions)}  run_at={stamp}")
    for key, v in summary.items():
        if key.count("|") == 1:
            print(f"{key:10} n={v['n']:2} Hit@1={v['hit@1']:6} EvidenceHit@3={v['evidence_hit@3']:6} "
                  f"page_hit@1={v['page_hit@1']:6} page_hit@3={v['page_hit@3']}")


POOL = 50                      # candidates taken from each retriever before fusion
HYBRID_DIR = config.RESULTS / "hybrid"
# tuning grid (dev only). 'dense' and 'bm25' are references, not selectable as "hybrid".
GRID = [("dense", {}), ("bm25", {}), ("rrf_k60", {"method": "rrf", "rrf_k": 60}),
        ("w0.3", {"method": "weighted", "alpha": 0.3}), ("w0.5", {"method": "weighted", "alpha": 0.5}),
        ("w0.7", {"method": "weighted", "alpha": 0.7}), ("w0.8", {"method": "weighted", "alpha": 0.8})]


def _hybrid_runner():
    """Returns run(question, system) -> trace for systems 'dense', 'bm25' and any grid name."""
    from .hybrid import BM25, fuse
    embedder, store = MyEmbedder(), _store()
    chunks = store.all_chunks("B2")
    by_id = {c["chunk_id"]: c for c in chunks}
    bm = BM25([c["text"] for c in chunks])          # idf/length statistics over the whole B2 index

    def run(q: dict, system: str, params: dict) -> dict:
        flt = q["filter"]                               # C2 convention: filter only when the question has one
        t0 = time.perf_counter()
        qv = embedder.embed_query(q["question"])
        dense = [(h["chunk_id"], h["score"]) for h in store.search("B2", qv, POOL, flt)]
        t_dense = time.perf_counter() - t0
        t1 = time.perf_counter()
        sc = bm.scores(q["question"])
        ranked = sorted(((c["chunk_id"], s) for c, s in zip(chunks, sc)
                         if s > 0 and all(c.get(k) == v for k, v in (flt or {}).items())),
                        key=lambda x: (-x[1], x[0]))[:POOL]
        t_bm = time.perf_counter() - t1
        method = params.get("method", system)
        fused = fuse(dense, ranked, method, params.get("alpha", 0.5), params.get("rrf_k", 60))[:config.TOP_K]
        dr = {c: i for i, (c, _) in enumerate(dense, 1)}
        br = {c: i for i, (c, _) in enumerate(ranked, 1)}
        ds, bs = dict(dense), dict(ranked)
        hits = [{**by_id[c], "score": s, "dense_rank": dr.get(c), "bm25_rank": br.get(c),
                 "dense_score": ds.get(c), "bm25_score": bs.get(c)} for c, s in fused]
        tr = evaluate_query(q, hits)
        tr.update({"strategy": system, "index": "B2", "filter_used": flt,
                   "dense_ms": round(t_dense * 1000, 1), "bm25_ms": round(t_bm * 1000, 2)})
        if flt:
            tr["filter_ok"] = all(h.get(k) == v for h in hits for k, v in flt.items())
        return tr
    return run


def cmd_hybrid_tune(_: argparse.Namespace) -> None:
    """Grid on the 15 DEV questions only; selects by a rule fixed here, then freezes the choice."""
    bench = json.loads(config.BENCHMARK.read_text())["questions"]
    dev = [q for q in bench if q["split"] == "dev"]
    run = _hybrid_runner()
    table = {}
    for name, params in GRID:
        traces = [run(q, name, params) for q in dev]
        table[name] = {"params": params, "hit@1": sum(t["hit@1"] for t in traces),
                       "hit@3": sum(t["hit@3"] for t in traces), "n": len(traces),
                       "per_question": {t["id"]: [int(t["hit@1"]), int(t["hit@3"])] for t in traces}}
        print(f"{name:8} dev Hit@1={table[name]['hit@1']}/15  Hit@3={table[name]['hit@3']}/15")
    # rule (fixed before running): among hybrids only -> max Hit@3, then max Hit@1, then RRF (no tuned weight),
    # then the larger dense weight alpha
    cand = [n for n in table if n not in ("dense", "bm25")]
    best = max(cand, key=lambda n: (table[n]["hit@3"], table[n]["hit@1"], n.startswith("rrf"),
                                    dict(GRID)[n].get("alpha", 0)))
    HYBRID_DIR.mkdir(parents=True, exist_ok=True)
    frozen_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    (HYBRID_DIR / "tuning_dev.json").write_text(json.dumps({"run_at": frozen_at, "pool": POOL, "table": table}, indent=1))
    (HYBRID_DIR / "frozen.json").write_text(json.dumps(
        {"frozen_at": frozen_at, "selected": best, "params": dict(GRID)[best], "pool": POOL,
         "bm25": {"k1": 1.5, "b": 0.75}, "selection_rule": "dev only: max Evidence Hit@3, then Hit@1, then RRF, then larger alpha"},
        indent=1))
    print(f"selected on dev: {best}  (frozen_at {frozen_at}); holdout/test not touched")


def cmd_hybrid_eval(args: argparse.Namespace) -> None:
    frozen_path = HYBRID_DIR / "frozen.json"
    if not frozen_path.exists():
        raise SystemExit("no frozen hybrid parameters: run `python -m src.run hybrid-tune` first")
    frozen = json.loads(frozen_path.read_text())
    data = json.loads(open(args.bench).read())["questions"]
    qs = [q for q in data if q["split"] == args.split]
    if args.split == "test" and not args.final:
        raise SystemExit("original test split is locked: pass --final")
    run = _hybrid_runner()
    systems = [("dense", {}), ("bm25", {}), ("hybrid", {**frozen["params"]})]
    traces = [run(q, name, p) for q in qs for name, p in systems]
    out = HYBRID_DIR / args.tag
    out.mkdir(parents=True, exist_ok=True)
    (out / "traces.jsonl").write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in traces) + "\n")
    summary = summarize(traces)
    (out / "summary.json").write_text(json.dumps({"frozen": frozen, "bench": args.bench, "split": args.split,
                                                  "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                                  "summary": summary}, indent=1))
    print(f"bench={args.bench} split={args.split} n={len(qs)} hybrid={frozen['selected']}")
    for key, v in summary.items():
        if key.count("|") == 1:
            print(f"{key:16} Hit@1={v['hit@1']:5}  EvidenceHit@3={v['evidence_hit@3']:5}  page_hit@3={v['page_hit@3']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest").set_defaults(fn=cmd_ingest)
    ev = sub.add_parser("eval")
    ev.add_argument("--split", choices=["dev", "test"], required=True)
    ev.add_argument("--tag", required=True, help="experiment name; results go to results/<tag>/")
    ev.add_argument("--final", action="store_true", help="required for the test split")
    ev.set_defaults(fn=cmd_eval)
    sub.add_parser("hybrid-tune").set_defaults(fn=cmd_hybrid_tune)
    he = sub.add_parser("hybrid-eval")
    he.add_argument("--bench", required=True)
    he.add_argument("--split", required=True)
    he.add_argument("--tag", required=True)
    he.add_argument("--final", action="store_true")
    he.set_defaults(fn=cmd_hybrid_eval)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
