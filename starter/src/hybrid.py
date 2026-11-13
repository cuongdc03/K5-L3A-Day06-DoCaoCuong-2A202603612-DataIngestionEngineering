"""Optional extension: hybrid retrieval = dense (pgvector) + BM25 keyword search.

Chunks, vectors and the metadata filter are exactly those of C2 (strategy B2). BM25 is a plain
Okapi implementation over the same chunk texts (k1=1.5, b=0.75: textbook defaults, NOT tuned).
Only the fusion method / weight is tuned, on the 15 dev questions (see run.py hybrid-tune).
"""
import math
import re
from collections import Counter

STOP = set("""a an the of to in on for and or is are was were be been being by with as at from that this
these those it its which what when who whom how why do does did can could may might must should would will
not no than then there their they them he she you your i we our us if into about over under between after
before during each any all both other such only same so very also have has had""".split())


def stem(word: str) -> str:
    """Light deterministic suffix stripping (applied to documents and queries alike)."""
    if len(word) > 4:
        for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
            if word.endswith(suffix) and len(word) - len(suffix) >= 3:
                return word[: -len(suffix)] + repl
    return word


def tokens(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


class BM25:
    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(t)) for t in texts]
        self.len = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.len) / len(self.len)
        df = Counter(w for d in self.docs for w in d)
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    def scores(self, query: str) -> list[float]:
        q = [w for w in tokens(query) if w in self.idf]
        out = []
        for d, ln in zip(self.docs, self.len):
            s = 0.0
            for w in q:
                f = d.get(w, 0)
                if f:
                    s += self.idf[w] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / self.avg))
            out.append(s)
        return out


def _minmax(pairs: list[tuple[str, float]]) -> dict[str, float]:
    if not pairs:
        return {}
    vals = [s for _, s in pairs]
    lo, hi = min(vals), max(vals)
    return {cid: (1.0 if hi == lo else (s - lo) / (hi - lo)) for cid, s in pairs}


def fuse(dense: list[tuple[str, float]], bm25: list[tuple[str, float]], method: str,
         alpha: float = 0.5, rrf_k: int = 60) -> list[tuple[str, float]]:
    """dense/bm25: (chunk_id, score) lists already sorted best-first. Returns fused ranking."""
    if method == "dense":
        return list(dense)
    if method == "bm25":
        return list(bm25)
    ids = {c for c, _ in dense} | {c for c, _ in bm25}
    if method == "rrf":
        rd = {c: i for i, (c, _) in enumerate(dense, 1)}
        rb = {c: i for i, (c, _) in enumerate(bm25, 1)}
        fused = {c: (1 / (rrf_k + rd[c]) if c in rd else 0.0) + (1 / (rrf_k + rb[c]) if c in rb else 0.0) for c in ids}
    elif method == "weighted":
        nd, nb = _minmax(dense), _minmax(bm25)
        fused = {c: alpha * nd.get(c, 0.0) + (1 - alpha) * nb.get(c, 0.0) for c in ids}
    else:
        raise ValueError(method)
    return sorted(fused.items(), key=lambda x: (-x[1], x[0]))
