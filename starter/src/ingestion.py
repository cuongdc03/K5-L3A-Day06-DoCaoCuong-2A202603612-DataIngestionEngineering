"""Read the PDF pages listed in the manifest, normalize text, keep source/page links."""
import json
import re
import unicodedata

import pymupdf

from . import config
from .models import DocumentPage

FOOTER = re.compile(r"Access for free at openstax\.org")


def norm(text: str) -> str:
    """Same normalization as scripts/build_manifest.py: NFC, strip footer, collapse spaces."""
    text = unicodedata.normalize("NFC", text)
    text = FOOTER.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_blocks(page: pymupdf.Page) -> list[dict]:
    """Layout blocks with a kind: header | heading | body | footnote.

    Font size is the signal (verified on p.55/67/153): body 9pt, headings 13pt+ bold,
    footnotes/captions 7.5pt, running header 7.5pt bold at the very top of the page.
    """
    blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue  # images
        spans = [s for l in b["lines"] for s in l["spans"]]
        text = norm("\n".join("".join(s["text"] for s in l["spans"]) for l in b["lines"]))
        if not text or not spans:
            continue
        size = max(s["size"] for s in spans)
        y0 = b["bbox"][1]
        if y0 < 45 and size < 8:
            kind = "header"          # running header, e.g. "1.8 • Other Types of Patents 47"
        elif size >= 12:
            kind = "heading"
        elif size < 8.5 and not re.match(r"(Figure|Table) \d", text) and y0 > 600:
            kind = "footnote"
        else:
            kind = "body"
        blocks.append({"kind": kind, "text": text, "y0": round(y0, 1)})
    return blocks


def load_pages() -> tuple[list[DocumentPage], list[str]]:
    """Return (pages, errors). Errors are logged, never silently ignored."""
    manifest = json.loads(config.MANIFEST.read_text())
    doc = pymupdf.open(config.PDF)
    pages, errors = [], []
    for rec in manifest["pages"]:
        n = rec["pdf_page"]
        try:
            raw = doc[n - 1]
            text = norm(raw.get_text())
            if len(text) != rec["chars"]:
                errors.append(f"p{n}: char count {len(text)} != manifest {rec['chars']}")
            pages.append(DocumentPage(
                document_id=config.DOCUMENT_ID, source=config.SOURCE_NAME, page=n, text=text,
                metadata={
                    "page_id": rec["page_id"], "printed_page": rec["printed_page"],
                    "chapter": rec["chapter"], "chapter_title": rec["chapter_title"],
                    "ip_type": rec["ip_type"], "section": rec["section_at_page_start"],
                    "blocks": extract_blocks(raw),
                }))
        except Exception as exc:  # noqa: BLE001 - record and continue
            errors.append(f"p{n}: {type(exc).__name__}: {exc}")
    return pages, errors
