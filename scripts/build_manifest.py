"""Build data/manifest.json for the OpenStax 'Introduction to Intellectual Property' PDF.

Usage: python scripts/build_manifest.py [pdf_path] [out_path]
Rule (fixed before any benchmark/retrieval run):
  a page counts as useful content if it lies inside the body of chapters 1-5
  (chapter start .. last page before that chapter's 'Assessment Questions')
  AND has >= MIN_CHARS normalized characters.
Excluded: cover/preface/TOC, assessment questions, glossary, answer key, index,
chapter-opener pages that only hold a figure + outline.
"""
import hashlib, json, re, sys, unicodedata
from datetime import datetime, timezone
import pymupdf

PDF = sys.argv[1] if len(sys.argv) > 1 else "data/raw/introduction-intellectual-property.pdf"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/manifest.json"
URL = "https://assets.openstax.org/oscms-prodcms/media/documents/introduction-intellectual-property_-_WEB.pdf"
MIN_CHARS = 700
PRINTED_OFFSET = 8  # printed page = PDF page - 8 (verified: PDF p.16 prints "8 Preface")


def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"Access for free at openstax\.org", "", t)
    return re.sub(r"\s+", " ", t).strip()


doc = pymupdf.open(PDF)
toc = doc.get_toc()
chapters = [(t, p) for l, t, p in toc if l == 1 and t.startswith("Chapter ")]
sections = [(t, p) for l, t, p in toc if l == 2 and re.match(r"\d+\.\d+ ", t)]
assess = [p for l, t, p in toc if l == 2 and t == "Assessment Questions"]
ip_type = {1: "patent", 2: "patent", 3: "copyright", 4: "trademark", 5: "trade_secret"}

pages, excluded = [], []
for ci, (ctitle, cstart) in enumerate(chapters):
    cnum = int(re.match(r"Chapter (\d+)", ctitle).group(1))
    cend = assess[ci] - 1  # last page before 'Assessment Questions' starts
    for p in range(cstart, assess[ci] + 1):
        text = norm(doc[p - 1].get_text())
        sec = [s for s in sections if s[1] <= p and int(s[0].split(".")[0]) == cnum]
        rec = {
            "page_id": f"ip-p{p:03d}", "pdf_page": p, "printed_page": p - PRINTED_OFFSET,
            "chapter": cnum, "chapter_title": ctitle.split(" ", 2)[2], "ip_type": ip_type[cnum],
            "section_at_page_start": sec[-1][0] if sec else None, "chars": len(text),
        }
        if p <= cend and len(text) >= MIN_CHARS:
            rec["sha256_text"] = hashlib.sha256(text.encode()).hexdigest()
            pages.append(rec)
        else:
            rec["reason"] = "assessment_questions" if p > cend else f"under_{MIN_CHARS}_chars"
            excluded.append(rec)

manifest = {
    "source_id": "openstax-intro-ip",
    "title": "Introduction to Intellectual Property (OpenStax)",
    "language": "en",
    "source_path_or_url": URL,
    "local_path": PDF,
    "license_or_permission": "CC BY 4.0 (OpenStax); attribution: OpenStax, Introduction to Intellectual Property",
    "publish_date_listed_by_openstax": "2021-02-22",
    "accessed_at": "2026-11-13T07:17:20Z",
    "file_sha256": hashlib.sha256(open(PDF, "rb").read()).hexdigest(),
    "physical_pages": doc.page_count,
    "extractor": f"pymupdf {pymupdf.__version__}",
    "counting_rule": f"body pages of chapters 1-5 (chapter start to before 'Assessment Questions') with >= {MIN_CHARS} normalized chars; "
                     "normalization = Unicode NFC, strip OpenStax footer, collapse whitespace",
    "excluded_ranges": "PDF p.1-16 front matter; assessment questions; glossary p.191-194; answer key p.195-200; index p.201",
    "useful_page_count": len(pages),
    "useful_chars": sum(p["chars"] for p in pages),
    "pages_per_chapter": {str(c): sum(1 for p in pages if p["chapter"] == c) for c in range(1, 6)},
    "pages": pages,
    "excluded_pages_inside_chapters": excluded,
    "errors": [],
    "note": "section_at_page_start = latest section heading that starts on or before the page; a page may contain several sections.",
}
json.dump(manifest, open(OUT, "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: manifest[k] for k in ["useful_page_count", "useful_chars", "pages_per_chapter", "file_sha256"]}, indent=1))
print("excluded inside chapters:", len(excluded))
