"""Automatic retrieval metrics with full per-query traces.

A hit = chunk is on an accepted gold page AND its text contains the whole evidence quote
(after whitespace normalization). Alternative equivalent evidence is NOT recognised here;
it is handled later by manual review, so these numbers are a strict lower bound.
Chunk coherence and grounding are manual labels and are never computed here.
"""
from collections import defaultdict
from typing import Any

from .ingestion import norm


def evaluate_query(question: dict[str, Any], hits: list[dict[str, Any]]) -> dict[str, Any]:
    quote = norm(question["evidence_quote"])
    accepted = set(question["gold_pages_accepted"])
    rows = []
    for rank, h in enumerate(hits, 1):
        page_ok = h["page"] in accepted
        evid_ok = quote in norm(h["text"])
        rows.append({**h, "rank": rank, "page_hit": page_ok, "evidence_in_chunk": evid_ok,
                     "hit": page_ok and evid_ok})
    return {
        "id": question["id"], "split": question["split"], "type": question["type"],
        "difficulty": question["difficulty"], "question": question["question"],
        "filter_used": None, "gold_pages_accepted": sorted(accepted),
        "evidence_quote": question["evidence_quote"], "hits": rows,
        "hit@1": bool(rows and rows[0]["hit"]),
        "hit@3": any(r["hit"] for r in rows),
        "page_hit@1": bool(rows and rows[0]["page_hit"]),
        "page_hit@3": any(r["page_hit"] for r in rows),
        "evidence_split": (not any(r["hit"] for r in rows)) and any(r["page_hit"] for r in rows),
    }


def summarize(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate by (strategy, split) with numerator/denominator, and by difficulty."""
    groups: dict[str, list] = defaultdict(list)
    for t in traces:
        groups[f"{t['strategy']}|{t['split']}"].append(t)
        groups[f"{t['strategy']}|{t['split']}|{t['difficulty']}"].append(t)
        if t["filter_used"]:
            groups[f"{t['strategy']}|{t['split']}|filtered"].append(t)
    out = {}
    for key, ts in sorted(groups.items()):
        n = len(ts)
        out[key] = {"n": n,
                    "hit@1": f"{sum(t['hit@1'] for t in ts)}/{n}",
                    "evidence_hit@3": f"{sum(t['hit@3'] for t in ts)}/{n}",
                    "page_hit@1": f"{sum(t['page_hit@1'] for t in ts)}/{n}",
                    "page_hit@3": f"{sum(t['page_hit@3'] for t in ts)}/{n}"}
    return out
