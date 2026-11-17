"""Idempotent ingestion of a Markdown KB into a vector store (ADR-0005)."""

from dataclasses import dataclass
from pathlib import Path

from talk_to_my_cv.chunking import Chunk, chunk_document
from talk_to_my_cv.embeddings import Embedder
from talk_to_my_cv.store import EmbeddingModel, VectorStore


@dataclass(frozen=True)
class IngestReport:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0


class EmbeddingModelMismatch(Exception):
    pass


def load_chunks(kb_dir: Path) -> list[Chunk]:
    """Every chunk of every Markdown file, except drafts (any path part starting with `_`)."""
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.rglob("*.md")):
        relative = path.relative_to(kb_dir)
        if any(part.startswith("_") for part in relative.parts):
            continue
        chunks.extend(chunk_document(path.relative_to(kb_dir).as_posix(), path.read_text()))
    return chunks


def _ensure_model(store: VectorStore, wanted: EmbeddingModel, rebuild: bool) -> None:
    if rebuild:
        store.reset()
    current = store.get_model()
    if current is None:
        store.set_model(wanted)
    elif current != wanted:
        raise EmbeddingModelMismatch(
            f"The index was built with {current.name} ({current.dimension} dims), "
            f"but EMBED_MODEL is {wanted.name} ({wanted.dimension} dims). Vectors from "
            "different models can't be compared: run `make ingest REBUILD=1` to start over."
        )


def ingest(
    kb_dir: Path, embedder: Embedder, store: VectorStore, rebuild: bool = False
) -> IngestReport:
    _ensure_model(store, EmbeddingModel(embedder.model, embedder.dimension), rebuild)

    chunks = load_chunks(kb_dir)
    stored = store.fingerprints()
    changed = [c for c in chunks if stored.get(c.id) != c.content_hash]
    if changed:
        store.upsert(changed, embedder.embed([c.embed_text for c in changed]))

    orphans = set(stored) - {c.id for c in chunks}
    if orphans:
        store.delete(orphans)

    added = sum(1 for c in changed if c.id not in stored)
    return IngestReport(
        added=added,
        updated=len(changed) - added,
        unchanged=len(chunks) - len(changed),
        deleted=len(orphans),
    )
