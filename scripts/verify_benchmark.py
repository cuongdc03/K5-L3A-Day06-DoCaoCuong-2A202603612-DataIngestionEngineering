"""Verify every benchmark evidence_quote exists in the gold page text (after the same
normalization used for the manifest) and that filters match the gold page metadata.

Usage: python scripts/verify_benchmark.py [pdf] [manifest] [benchmark]
Exit code 1 if any check fails.
"""
import json, re, sys, unicodedata
from collections import Counter
import pymupdf

PDF = sys.argv[1] if len(sys.argv) > 1 else "data/raw/introduction-intellectual-property.pdf"
MAN = sys.argv[2] if len(sys.argv) > 2 else "data/manifest.json"
BEN = sys.argv[3] if len(sys.argv) > 3 else "data/benchmark.json"


def norm(t):
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"Access for free at openstax\.org", "", t)
    return re.sub(r"\s+", " ", t).strip()


doc = pymupdf.open(PDF)
man = {p["pdf_page"]: p for p in json.load(open(MAN))["pages"]}
bench = json.load(open(BEN))
qs = bench["questions"]
fails = []
for q in qs:
    qid, quote = q["id"], norm(q["evidence_quote"])
    pages = q["gold_pages_accepted"]
    if q["gold_page"] not in pages:
        fails.append(f"{qid}: gold_page not in gold_pages_accepted")
    for p in pages:
        if p not in man:
            fails.append(f"{qid}: page {p} is not a counted corpus page")
    # the primary evidence must be in at least one accepted page; primary page must contain it
    gp = q["gold_page"]
    if quote not in norm(doc[gp - 1].get_text()):
        fails.append(f"{qid}: evidence_quote NOT found on gold_page {gp}")
    if q["filter"]:
        for k, v in q["filter"].items():
            for p in pages:
                if man[p].get(k) != v:
                    fails.append(f"{qid}: filter {k}={v} but page {p} has {man[p].get(k)}")

by_split = Counter(q["split"] for q in qs)
print("total", len(qs), dict(by_split))
print("difficulty", dict(Counter(q["difficulty"] for q in qs)))
print("type", dict(Counter(q["type"] for q in qs)))
filt = [q for q in qs if q["filter"]]
print("filter questions:", len(filt), "dev", sum(q["split"] == "dev" for q in filt), "test", sum(q["split"] == "test" for q in filt))
print("gold pages per chapter:", dict(Counter(man[q["gold_page"]]["chapter"] for q in qs)))
print("gold ip_type:", dict(Counter(man[q["gold_page"]]["ip_type"] for q in qs)))
print("PASS" if not fails else "FAIL")
for f in fails:
    print(" -", f)
sys.exit(1 if fails else 0)
