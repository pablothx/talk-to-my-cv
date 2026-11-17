"""One contract, every store: the in-memory fake must behave like the real ones."""

import math

import pytest

from talk_to_my_cv.chunking import Chunk
from talk_to_my_cv.config import load_settings
from talk_to_my_cv.store import (
    EmbeddingModel,
    InMemoryStore,
    SearchMode,
    UnsupportedSearchMode,
)

MODEL = EmbeddingModel(name="fake-embed", dimension=3)


def _chunk(id_: str, text: str = "text", content_hash: str = "h1") -> Chunk:
    return Chunk(
        id=id_,
        content_hash=content_hash,
        file="profile.md",
        section=f"Section {id_}",
        text=text,
        embed_text=text,
        metadata={"type": "profile"},
    )


def _unit(*xs: float) -> list[float]:
    norm = math.hypot(*xs)
    return [x / norm for x in xs]


def _pgvector_store():
    from talk_to_my_cv.store import PgVectorStore

    store = PgVectorStore(load_settings().database_url, schema="test_contract")
    store.reset()
    return store


@pytest.fixture(
    params=[
        pytest.param(InMemoryStore, id="memory"),
        pytest.param(_pgvector_store, id="pgvector", marks=pytest.mark.e2e),
    ]
)
def store(request):
    store = request.param()
    store.set_model(MODEL)
    return store


def test_search_returns_closest_chunks_first_with_scores_between_0_and_1(store):
    store.upsert(
        [_chunk("a"), _chunk("b"), _chunk("c")],
        [_unit(1, 0, 0), _unit(1, 1, 0), _unit(0, 0, 1)],
    )

    results = store.search("query", _unit(1, 0.1, 0), mode=SearchMode.VECTOR, k=2)

    assert [r.chunk.id for r in results] == ["a", "b"]
    assert all(0.0 <= r.score <= 1.0 for r in results)
    assert results[0].score > results[1].score
    assert results[0].chunk == _chunk("a")


def test_upsert_with_the_same_id_replaces(store):
    store.upsert([_chunk("a", "old", "h1")], [_unit(1, 0, 0)])
    store.upsert([_chunk("a", "new", "h2")], [_unit(1, 0, 0)])

    assert store.fingerprints() == {"a": "h2"}
    [result] = store.search("q", _unit(1, 0, 0), mode=SearchMode.VECTOR, k=5)
    assert result.chunk.text == "new"


def test_delete_removes_chunks(store):
    store.upsert([_chunk("a"), _chunk("b")], [_unit(1, 0, 0), _unit(0, 1, 0)])

    store.delete(["a"])

    assert set(store.fingerprints()) == {"b"}


@pytest.mark.parametrize("mode", [SearchMode.KEYWORD, SearchMode.HYBRID])
def test_keyword_and_hybrid_are_not_supported_yet(store, mode):
    with pytest.raises(UnsupportedSearchMode):
        store.search("q", _unit(1, 0, 0), mode=mode, k=5)


def test_embedding_model_is_remembered(store):
    assert store.get_model() == MODEL


def test_reset_forgets_chunks_and_model(store):
    store.upsert([_chunk("a")], [_unit(1, 0, 0)])

    store.reset()

    assert store.get_model() is None
    assert store.fingerprints() == {}
