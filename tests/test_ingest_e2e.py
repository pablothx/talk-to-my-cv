"""Ingest kb.example/ into a real pgvector schema with the real bge-m3."""

from pathlib import Path

import pytest
from fakes import FakeEmbedder

from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder
from talk_to_my_cv.ingest import EmbeddingModelMismatch, ingest
from talk_to_my_cv.store import PgVectorStore

pytestmark = pytest.mark.e2e

KB = Path(__file__).resolve().parents[1] / "kb.example"


@pytest.fixture
def store():
    store = PgVectorStore(load_settings().database_url, schema="test_ingest")
    store.reset()
    return store


def test_kb_example_ingests_and_a_rerun_changes_nothing(store):
    embedder = build_embedder(load_settings())

    first = ingest(KB, embedder, store)
    second = ingest(KB, embedder, store)

    assert first.added > 0
    assert (second.added, second.updated, second.deleted) == (0, 0, 0)
    assert second.unchanged == first.added


def test_switching_embedding_model_fails_pointing_to_rebuild(store):
    ingest(KB, build_embedder(load_settings()), store)

    with pytest.raises(EmbeddingModelMismatch, match=r"make ingest REBUILD=1"):
        ingest(KB, FakeEmbedder(model="other-model", dimension=1024), store)
