"""One contract, every store: the in-memory fake must behave like the real ones."""

import math

import pytest

from talk_to_my_cv.chunking import Chunk
from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import cosine_similarity
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


def _opensearch_store():
    from talk_to_my_cv.store_opensearch import OpenSearchStore

    store = OpenSearchStore(load_settings().opensearch_url, index="test-contract")
    store.reset()
    return store


@pytest.fixture(
    params=[
        pytest.param(InMemoryStore, id="memory"),
        pytest.param(_pgvector_store, id="pgvector", marks=pytest.mark.e2e),
        pytest.param(_opensearch_store, id="opensearch", marks=pytest.mark.e2e),
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
    # The score is the cosine similarity itself, in every store: the gate depends on it.
    assert results[0].score == pytest.approx(cosine_similarity(_unit(1, 0.1, 0), _unit(1, 0, 0)))
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


@pytest.mark.parametrize("mode", list(SearchMode))
def test_unsupported_modes_raise_and_supported_ones_answer(store, mode):
    store.upsert([_chunk("a")], [_unit(1, 0, 0)])

    if mode not in store.supported_modes:
        with pytest.raises(UnsupportedSearchMode):
            store.search("q", _unit(1, 0, 0), mode=mode, k=5)
    else:
        assert store.search("text", _unit(1, 0, 0), mode=mode, k=5)


def test_keyword_search_finds_the_exact_term_the_vectors_miss(store):
    if SearchMode.KEYWORD not in store.supported_modes:
        pytest.skip("store has no keyword search")
    store.upsert(
        [_chunk("java", "Java 21 and Kotlin."), _chunk("k8s", "Never used Kubernetes.")],
        [_unit(1, 0, 0), _unit(0, 1, 0)],
    )

    results = store.search("Did she use Kubernetes?", _unit(1, 0, 0), mode=SearchMode.KEYWORD, k=5)

    assert [r.chunk.id for r in results] == ["k8s"]
    assert results[0].score == pytest.approx(0.0, abs=1e-6)  # still cosine, not BM25


def test_hybrid_combines_both_signals(store):
    if SearchMode.HYBRID not in store.supported_modes:
        pytest.skip("store has no hybrid search")
    store.upsert(
        [_chunk("java", "Java 21 and Kotlin."), _chunk("k8s", "Never used Kubernetes.")],
        [_unit(1, 0, 0), _unit(0, 1, 0)],
    )

    results = store.search("Did she use Kubernetes?", _unit(1, 0.2, 0), mode=SearchMode.HYBRID, k=5)

    assert {r.chunk.id for r in results} == {"java", "k8s"}
    assert results[0].chunk.id == "k8s"  # the exact term outweighs a closer vector


def test_question_words_alone_do_not_match(store):
    if SearchMode.KEYWORD not in store.supported_modes:
        pytest.skip("store has no keyword search")
    store.upsert([_chunk("a", "She led the team, with care.")], [_unit(1, 0, 0)])

    results = store.search(
        "Has she worked with JavaScript?", _unit(1, 0, 0), mode=SearchMode.KEYWORD, k=5
    )

    assert results == []
