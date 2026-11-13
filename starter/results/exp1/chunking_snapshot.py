"""Fixed-size (A) and structure-aware (B/C) chunking. Chunks never cross a page, so every
chunk keeps exactly one source page."""
import hashlib
import re

from .models import Chunk, DocumentPage

SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


def _meta(page: DocumentPage, idx: int, kind: str) -> dict:
    m = {k: v for k, v in page.metadata.items() if k != "blocks"}
    m.update({"chunk_index": idx, "kind": kind})
    return m


def _make(strategy: str, page: DocumentPage, idx: int, text: str, kind: str = "body") -> Chunk:
    return Chunk(chunk_id=f"{strategy}-p{page.page:03d}-{idx:02d}", document_id=page.document_id,
                 source=page.source, page=page.page, text=text, metadata=_meta(page, idx, kind))


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Overlapping character windows over the normalized page text (no structure used)."""
    text, out, start = page.text, [], 0
    while start < len(text):
        piece = text[start:start + size]
        out.append(_make("A", page, len(out), piece))
        if start + size >= len(text):
            break
        start += size - overlap
    return out


def _split_long(text: str, max_size: int) -> list[str]:
    """Split an oversized paragraph on sentence boundaries; hard-split only as last resort."""
    parts, cur = [], ""
    for sent in SENTENCE.split(text):
        while len(sent) > max_size:           # a single sentence longer than the limit
            cut = sent.rfind(" ", 0, max_size)
            cut = max_size if cut <= 0 else cut
            parts.append(sent[:cut]); sent = sent[cut:].lstrip()
        if cur and len(cur) + 1 + len(sent) > max_size:
            parts.append(cur); cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return parts


MIN_CHUNK = 80   # fragments shorter than this are merged into the previous chunk of the same kind


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Group layout blocks of one page. A heading starts a new chunk and stays with the text
    that follows it (consecutive headings are kept together); footnotes form their own chunks
    (kind='footnote'). Tiny non-heading fragments are merged into the previous same-kind chunk
    when it still fits."""
    out: list[Chunk] = []
    led_by_heading: list[bool] = []
    cur: list[str] = []
    cur_kind = "body"
    cur_heading = False                       # current chunk started with a heading
    heading_only = False                      # chunk holds only heading text so far

    def flush() -> None:
        nonlocal cur, heading_only, cur_heading
        if cur:
            text = " ".join(cur)
            if (not cur_heading and len(text) < MIN_CHUNK and out and out[-1].metadata["kind"] == cur_kind
                    and len(out[-1].text) + 1 + len(text) <= max_size):
                out[-1].text += " " + text
            else:
                out.append(_make("B", page, len(out), text, cur_kind))
                led_by_heading.append(cur_heading)
        cur, heading_only, cur_heading = [], False, False

    for blk in page.metadata["blocks"]:
        kind, text = blk["kind"], blk["text"]
        if kind == "header":
            continue
        if kind == "heading":
            if heading_only:                  # heading directly after a heading: keep together
                cur.append(text)
            else:
                flush(); cur_kind = "body"; cur = [text]; heading_only = True; cur_heading = True
            continue
        want = "footnote" if kind == "footnote" else "body"
        if want != cur_kind:
            flush(); cur_kind = want
        pieces = _split_long(text, max_size) if len(text) > max_size else [text]
        for piece in pieces:
            if cur and not heading_only and len(" ".join(cur)) + 1 + len(piece) > max_size:
                flush()
            cur.append(piece)
            heading_only = False
    flush()
    return out


def content_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()
