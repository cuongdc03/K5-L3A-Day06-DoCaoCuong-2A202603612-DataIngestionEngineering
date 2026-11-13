"""Generate blank manual-labelling sheets (run from starter/: python scripts/make_manual_sheets.py).

Labels are NEVER filled here. Helper columns named auto_* are mechanical checks to speed up
verification; they do not replace the human judgement and must not be copied as labels.

Sampling rule for chunk coherence (fixed before any score is seen):
  take the 146 counted pages in page order, keep indexes 0, 15, 30, ..., 135 (10 pages spread
  over all five chapters); in each page the position is the sentence that starts closest to the
  middle of the body text (80-char anchor). Every strategy is judged on the chunk that contains
  that anchor. C2 uses the same chunks as B2, so it is scored once as B2/C2.
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")
from src import config                         # noqa: E402
from src.chunking import fixed_size           # noqa: E402
from src.ingestion import load_pages, norm    # noqa: E402
from src.run import _store                    # noqa: E402

OUT = config.RESULTS / "manual"
OUT.mkdir(parents=True, exist_ok=True)


def _guard() -> None:
    """Never overwrite sheets that already contain labels (author's work)."""
    for name in ("coherence_sheet.csv", "metadata_sheet.csv", "grounding_sheet.csv"):
        path = OUT / name
        if path.exists() and "--force" not in sys.argv:
            rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
            filled = any(v.strip() for r in rows for k, v in r.items() if "(FILL" in k and v)
            if filled:
                sys.exit(f"{name} already contains labels; refusing to overwrite (pass --force to regenerate blanks)")


_guard()


def write(name: str, header: list[str], rows: list[list]) -> None:
    with open(OUT / name, "w", newline="", encoding="utf-8-sig") as f:   # BOM: opens cleanly in Excel
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def body_text(page) -> str:
    return " ".join(b["text"] for b in page.metadata["blocks"] if b["kind"] != "header")


def anchor_of(text: str) -> tuple[str, int]:
    mid = len(text) // 2
    starts = [0] + [m.end() for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z“\"(])", text)]
    start = min(starts, key=lambda s: abs(s - mid))
    return text[start:start + 80], start


pages, errors = load_pages()
assert not errors, errors
store = _store()

# ---------------------------------------------------------------- 1. coherence
sample = [pages[i] for i in range(0, 146, 15)]
rows, positions, problems = [], [], []
for n, p in enumerate(sample, 1):
    text = body_text(p)
    anchor, off = anchor_of(text)
    positions.append({"position_id": f"pos{n:02d}", "pdf_page": p.page, "chapter": p.metadata["chapter"],
                      "anchor_80chars": anchor})
    page_ctx = text[max(0, off - 400): off + 600]
    for strat, db_strat in (("A", "A"), ("B2/C2", "B2")):
        db = store.conn.execute("SELECT chunk_id, text FROM chunks WHERE strategy=%s AND page=%s ORDER BY chunk_index",
                                (db_strat, p.page)).fetchall()
        hit = [(cid, t) for cid, t in db if anchor[:40] in norm(t)]
        if not hit:  # anchor split across two windows: take the chunk where it starts
            hit = [(cid, t) for cid, t in db if anchor[:20] in norm(t)]
        if not hit:
            problems.append(f"pos{n:02d} {strat}: anchor not found"); continue
        cid, t = hit[0]
        rows.append([f"pos{n:02d}", p.page, p.metadata["chapter"], strat, cid, len(t), anchor, t, page_ctx,
                     "", ""])
write("coherence_sheet.csv",
      ["position_id", "pdf_page", "chapter", "strategy", "chunk_id", "n_chars", "anchor_sentence",
       "chunk_text", "page_context_around_anchor", "score_0_1_2 (FILL)", "reason (FILL)"], rows)
(OUT / "coherence_positions.json").write_text(json.dumps({
    "rule": __doc__, "positions": positions, "problems": problems}, indent=1, ensure_ascii=False))

# ---------------------------------------------------------------- 2/3. metadata + grounding (5 test q)
bench = {q["id"]: q for q in json.loads(config.BENCHMARK.read_text())["questions"]}
traces = [json.loads(l) for l in open(config.RESULTS / "final" / "traces_test.jsonl")]
traces = [t for t in traces if t["strategy"] in ("A", "B2", "C2")]
order = {"A": 0, "B2": 1, "C2": 2}
traces.sort(key=lambda t: (t["id"], order[t["strategy"]]))
pdf_text = {p.page: p.text for p in pages}

meta_rows, ground_rows = [], []
for t in traces:
    q = bench[t["id"]]
    for h in t["hits"]:
        on_page = norm(h["text"])[:60] in pdf_text[h["page"]]
        meta_rows.append([t["id"], t["strategy"], h["rank"], h["chunk_id"], h["source"], h["page"],
                          h["printed_page"], h["chapter"], h["ip_type"], h["section"], h["kind"],
                          json.dumps(t["filter_used"]) if t["filter_used"] else "none",
                          "yes" if on_page else "NO", "yes" if (not t["filter_used"] or all(h.get(k) == v for k, v in t["filter_used"].items())) else "NO",
                          "", "", "", "", ""])
    texts = "\n\n".join(f"[rank {h['rank']} | p{h['page']} | {h['chunk_id']} | score {h['score']:.3f}]\n{h['text']}"
                        for h in t["hits"])
    ground_rows.append([t["id"], t["strategy"], q["question"], q["expected_answer"], q["evidence_quote"],
                        ",".join(map(str, q["gold_pages_accepted"])),
                        json.dumps(t["filter_used"]) if t["filter_used"] else "none", texts,
                        f"hit@3={int(t['hit@3'])} page_hit@3={int(t['page_hit@3'])}", "", ""])
write("metadata_sheet.csv",
      ["question_id", "strategy", "rank", "chunk_id", "source", "page", "printed_page", "chapter", "ip_type",
       "section_at_page_start", "kind", "filter_required", "auto_chunk_text_found_on_that_pdf_page",
       "auto_filter_satisfied", "source_correct (FILL y/n)", "page_correct (FILL y/n)",
       "ip_type_correct (FILL y/n)", "record_complete_and_correct (FILL y/n)", "error_note (FILL)"], meta_rows)
write("grounding_sheet.csv",
      ["question_id", "strategy", "question", "expected_answer", "gold_evidence_quote", "gold_pages",
       "filter_required", "top3_chunks", "auto_hint (do not copy)", "score_0_1_2 (FILL)", "reason (FILL)"],
      ground_rows)

print("coherence rows:", len(rows), "positions:", [(p["position_id"], p["pdf_page"]) for p in positions])
print("problems:", problems)
print("metadata rows:", len(meta_rows), " grounding rows:", len(ground_rows))
