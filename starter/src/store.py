"""PostgreSQL 16 + pgvector 0.8.7. Exact (sequential) cosine search: no ANN index is created,
so results are exact for this corpus size. Filters run in SQL, before ranking."""
from typing import Any

import psycopg

from .chunking import content_hash
from .models import Chunk

ALLOWED_FILTERS = {"ip_type", "chapter"}      # whitelist: column names are never user input


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in v) + "]"


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        self.dimensions = dimensions
        # autocommit: without it a SELECT opens an implicit transaction and conn.transaction()
        # becomes a savepoint that is rolled back when the process exits (data silently lost).
        self.conn = psycopg.connect(database_url, autocommit=True)   # raises if backend is down
        self.conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

    def create_schema(self) -> None:
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS chunks (
                strategy text NOT NULL, chunk_id text NOT NULL,
                document_id text NOT NULL, source text NOT NULL,
                page int NOT NULL, printed_page int, chapter int, ip_type text,
                section text, kind text, chunk_index int,
                text text NOT NULL, n_chars int NOT NULL, content_hash text NOT NULL,
                embedding vector({self.dimensions}) NOT NULL,
                PRIMARY KEY (strategy, chunk_id))""")
        self.conn.execute("CREATE INDEX IF NOT EXISTS chunks_filter ON chunks (strategy, ip_type)")
        self.conn.commit()

    def existing_hashes(self, strategy: str) -> dict[str, str]:
        rows = self.conn.execute("SELECT chunk_id, content_hash FROM chunks WHERE strategy=%s",
                                 (strategy,)).fetchall()
        return dict(rows)

    def count(self, strategy: str) -> int:
        return self.conn.execute("SELECT count(*) FROM chunks WHERE strategy=%s", (strategy,)).fetchone()[0]

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]]) -> int:
        """Write by stable chunk_id: re-running never duplicates rows. Does not delete anything;
        call prune() with the full current chunk-id list to drop obsolete chunks."""
        if len(chunks) != len(vectors):
            raise ValueError("chunks/vectors length mismatch")
        for v in vectors:
            if len(v) != self.dimensions:
                raise ValueError(f"vector dim {len(v)} != {self.dimensions}")
        with self.conn.transaction():
            for c, v in zip(chunks, vectors):
                m = c.metadata
                self.conn.execute("""
                    INSERT INTO chunks VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                    ON CONFLICT (strategy, chunk_id) DO UPDATE SET
                      text=EXCLUDED.text, n_chars=EXCLUDED.n_chars, content_hash=EXCLUDED.content_hash,
                      embedding=EXCLUDED.embedding, section=EXCLUDED.section, kind=EXCLUDED.kind""",
                    (strategy, c.chunk_id, c.document_id, c.source, c.page, m.get("printed_page"),
                     m.get("chapter"), m.get("ip_type"), m.get("section"), m.get("kind"),
                     m.get("chunk_index"), c.text, len(c.text), content_hash(c.text), _vec(v)))
        return len(chunks)

    def prune(self, strategy: str, keep_ids: list[str]) -> int:
        """Delete chunks of this strategy that are no longer produced (changed/removed source)."""
        with self.conn.transaction():
            return self.conn.execute("DELETE FROM chunks WHERE strategy=%s AND NOT (chunk_id = ANY(%s))",
                                     (strategy, keep_ids)).rowcount

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        where, params = ["strategy=%s"], [strategy]
        for key, value in (filters or {}).items():
            if key not in ALLOWED_FILTERS:
                raise ValueError(f"filter field not allowed: {key}")
            where.append(f"{key}=%s"); params.append(value)
        q = _vec(query_vector)
        rows = self.conn.execute(f"""
            SELECT chunk_id, text, 1 - (embedding <=> %s::vector) AS score, document_id, source, page,
                   printed_page, chapter, ip_type, section, kind
            FROM chunks WHERE {' AND '.join(where)}
            ORDER BY embedding <=> %s::vector LIMIT %s""", [q, *params, q, top_k]).fetchall()
        keys = ["chunk_id", "text", "score", "document_id", "source", "page", "printed_page",
                "chapter", "ip_type", "section", "kind"]
        return [dict(zip(keys, r)) for r in rows]
