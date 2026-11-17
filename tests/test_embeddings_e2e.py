"""Against the real Ollama + bge-m3. Run with `make test-e2e`."""

import pytest

from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder, cosine_similarity

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def score():
    embedder = build_embedder(load_settings())

    def _score(a: str, b: str) -> float:
        va, vb = embedder.embed([a, b])
        return cosine_similarity(va, vb)

    return _score


def test_bge_m3_returns_1024_dimensions():
    [vector] = build_embedder(load_settings()).embed(["hello"])

    assert len(vector) == 1024


def test_paraphrase_scores_higher_than_unrelated_sentence(score):
    query = "She led the migration of the payments service to AWS."
    paraphrase = "She was in charge of moving the payments system to Amazon's cloud."
    unrelated = "The recipe needs two cups of flour and a pinch of salt."

    assert score(query, paraphrase) > score(query, unrelated)


def test_spanish_and_its_english_translation_score_higher_than_unrelated(score):
    spanish = "Lideró la migración del servicio de pagos a AWS."
    english = "She led the migration of the payments service to AWS."
    unrelated = "The recipe needs two cups of flour and a pinch of salt."

    assert score(spanish, english) > score(spanish, unrelated)
