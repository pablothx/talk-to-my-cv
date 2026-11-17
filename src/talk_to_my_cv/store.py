"""Vector stores behind one interface (ADR-0005, ADR-0007)."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.types.json import Jsonb

from talk_to_my_cv.chunking import Chunk
from talk_to_my_cv.embeddings import Vector, cosine_similarity


class SearchMode(StrEnum):
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"


class UnsupportedSearchMode(Exception):
    def __init__(self, store: str, mode: SearchMode):
        super().__init__(f"{store} does not support {mode.value!r} search (yet)")


@dataclass(frozen=True)
class EmbeddingModel:
    """The model that produced the stored vectors. Vectors from different models don't mix."""

    name: str
    dimension: int


@dataclass(frozen=True)
class SearchResult:
    chunk: Chunk
    score: float


class VectorStore(Protocol):
    def get_model(self) -> EmbeddingModel | None: ...
    def set_model(self, model: EmbeddingModel) -> None: ...
    def fingerprints(self) -> dict[str, str]: ...
    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None: ...
    def delete(self, ids: Iterable[str]) -> None: ...
    def search(
        self, query: str, query_vector: Vector, mode: SearchMode, k: int
    ) -> list[SearchResult]: ...
    def reset(self) -> None: ...


class InMemoryStore:
    """A dict-backed store for unit tests. Same contract as the real ones."""

    def __init__(self) -> None:
        self.reset()

    def get_model(self) -> EmbeddingModel | None:
        return self._model

    def set_model(self, model: EmbeddingModel) -> None:
        self._model = model

    def fingerprints(self) -> dict[str, str]:
        return {id_: chunk.content_hash for id_, (chunk, _) in self._rows.items()}

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self._rows[chunk.id] = (chunk, list(vector))

    def delete(self, ids: Iterable[str]) -> None:
        for id_ in ids:
            self._rows.pop(id_, None)

    def search(
        self, query: str, query_vector: Vector, mode: SearchMode, k: int
    ) -> list[SearchResult]:
        if mode != SearchMode.VECTOR:
            raise UnsupportedSearchMode("InMemoryStore", mode)
        scored = [
            SearchResult(chunk, max(0.0, cosine_similarity(query_vector, vector)))
            for chunk, vector in self._rows.values()
        ]
        return sorted(scored, key=lambda r: r.score, reverse=True)[:k]

    def reset(self) -> None:
        self._model: EmbeddingModel | None = None
        self._rows: dict[str, tuple[Chunk, list[float]]] = {}


class PgVectorStore:
    """Postgres + pgvector. Creates its own schema on first use (ADR-0005)."""

    def __init__(self, url: str, schema: str = "public") -> None:
        self.url = url
        self.schema = sql.Identifier(schema)
        with self._connect(register=False) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(self.schema))
            conn.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {}.kb_meta "
                    "(model text NOT NULL, dimension int NOT NULL)"
                ).format(self.schema)
            )

    def _connect(self, register: bool = True) -> psycopg.Connection:
        conn = psycopg.connect(self.url, autocommit=True)
        if register:
            register_vector(conn)
        return conn

    def _q(self, template: str) -> sql.Composed:
        return sql.SQL(template).format(schema=self.schema)

    def get_model(self) -> EmbeddingModel | None:
        with self._connect(register=False) as conn:
            row = conn.execute(self._q("SELECT model, dimension FROM {schema}.kb_meta")).fetchone()
        return EmbeddingModel(*row) if row else None

    def set_model(self, model: EmbeddingModel) -> None:
        with self._connect(register=False) as conn:
            conn.execute(self._q("DELETE FROM {schema}.kb_meta"))
            conn.execute(
                self._q("INSERT INTO {schema}.kb_meta (model, dimension) VALUES (%s, %s)"),
                (model.name, model.dimension),
            )
            conn.execute(
                sql.SQL(
                    "CREATE TABLE IF NOT EXISTS {schema}.chunks ("
                    " id text PRIMARY KEY, content_hash text NOT NULL,"
                    " file text NOT NULL, section text NOT NULL,"
                    " text text NOT NULL, embed_text text NOT NULL,"
                    " metadata jsonb NOT NULL, embedding vector({dim}) NOT NULL)"
                ).format(schema=self.schema, dim=sql.Literal(model.dimension))
            )

    def _has_chunks_table(self, conn: psycopg.Connection) -> bool:
        return conn.execute(
            "SELECT to_regclass(%s) IS NOT NULL", (f"{self.schema.as_string()}.chunks",)
        ).fetchone()[0]

    def fingerprints(self) -> dict[str, str]:
        with self._connect(register=False) as conn:
            if not self._has_chunks_table(conn):
                return {}
            return dict(conn.execute(self._q("SELECT id, content_hash FROM {schema}.chunks")))

    def upsert(self, chunks: Sequence[Chunk], vectors: Sequence[Vector]) -> None:
        rows = [
            (
                c.id,
                c.content_hash,
                c.file,
                c.section,
                c.text,
                c.embed_text,
                Jsonb(c.metadata),
                np.array(v, dtype=np.float32),
            )
            for c, v in zip(chunks, vectors, strict=True)
        ]
        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                self._q(
                    "INSERT INTO {schema}.chunks VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET content_hash = EXCLUDED.content_hash,"
                    " file = EXCLUDED.file, section = EXCLUDED.section, text = EXCLUDED.text,"
                    " embed_text = EXCLUDED.embed_text, metadata = EXCLUDED.metadata,"
                    " embedding = EXCLUDED.embedding"
                ),
                rows,
            )

    def delete(self, ids: Iterable[str]) -> None:
        with self._connect(register=False) as conn:
            conn.execute(self._q("DELETE FROM {schema}.chunks WHERE id = ANY(%s)"), (list(ids),))

    def search(
        self, query: str, query_vector: Vector, mode: SearchMode, k: int
    ) -> list[SearchResult]:
        if mode != SearchMode.VECTOR:
            raise UnsupportedSearchMode("PgVectorStore", mode)
        with self._connect() as conn:
            rows = conn.execute(
                self._q(
                    "SELECT id, content_hash, file, section, text, embed_text, metadata,"
                    " GREATEST(0, 1 - (embedding <=> %s)) AS score"
                    " FROM {schema}.chunks ORDER BY embedding <=> %s LIMIT %s"
                ),
                (np.array(query_vector, dtype=np.float32),) * 2 + (k,),
            ).fetchall()
        return [SearchResult(Chunk(*row[:7]), float(row[7])) for row in rows]

    def reset(self) -> None:
        with self._connect(register=False) as conn:
            conn.execute(self._q("DROP TABLE IF EXISTS {schema}.chunks"))
            conn.execute(self._q("DELETE FROM {schema}.kb_meta"))
