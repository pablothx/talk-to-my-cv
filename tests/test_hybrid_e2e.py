"""OpenSearch on kb.example/: same scores as pgvector, and what BM25 adds (or doesn't)."""

from pathlib import Path

import pytest

from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder
from talk_to_my_cv.ingest import ingest
from talk_to_my_cv.store import SearchMode, build_store

pytestmark = pytest.mark.e2e

KB = Path(__file__).resolve().parents[1] / "kb.example"


@pytest.fixture(scope="module")
def stores():
    settings = load_settings()
    embedder = build_embedder(settings)
    built = {}
    for name in ("pgvector", "opensearch"):
        store = build_store(name, settings, namespace="test_hybrid")
        ingest(KB, embedder, store)
        built[name] = store

    def search(store: str, question: str, mode: SearchMode = SearchMode.VECTOR, k: int = 5):
        return built[store].search(question, embedder.embed([question])[0], mode=mode, k=k)

    return search


def test_vector_search_gives_the_same_top_1_and_score_in_both_stores(stores):
    question = "¿Usó Kubernetes?"

    [pg] = stores("pgvector", question, k=1)
    [os_] = stores("opensearch", question, k=1)

    assert pg.chunk.id == os_.chunk.id
    assert os_.score == pytest.approx(pg.score, abs=1e-3)


def test_keyword_search_finds_nothing_for_a_term_the_kb_never_mentions(stores):
    assert stores("opensearch", "Has she worked with JavaScript?", SearchMode.KEYWORD) == []


def test_hybrid_puts_the_lexical_match_first_where_vectors_did_not(stores):
    question = "How big is the team she leads?"
    expected = "Senior Backend Engineer"

    vector = stores("opensearch", question, SearchMode.VECTOR)
    hybrid = stores("opensearch", question, SearchMode.HYBRID)

    assert vector[0].chunk.section != expected
    assert hybrid[0].chunk.section == expected
