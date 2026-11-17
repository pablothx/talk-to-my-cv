import pytest
from fakes import FakeChatModel, FakeEmbedder

from talk_to_my_cv.chunking import Chunk, chunk_document
from talk_to_my_cv.rag import answer, is_refusal, refusal_for
from talk_to_my_cv.store import EmbeddingModel, InMemoryStore, SearchResult

KB = {
    "experience/northwind.md": "---\ntitle: Northwind\n---\n## Lumen\n\nLed Project Lumen.\n",
    "skills.md": "---\ntitle: Skills\n---\n## Languages\n\nJava.\n\n## Cloud\n\nAWS.\n",
}


@pytest.fixture
def store():
    embedder, store = FakeEmbedder(), InMemoryStore()
    store.set_model(EmbeddingModel(embedder.model, embedder.dimension))
    chunks = [c for path, md in KB.items() for c in chunk_document(path, md)]
    store.upsert(chunks, embedder.embed([c.embed_text for c in chunks]))
    return store


def test_answer_retrieves_top_k_and_hands_them_to_the_chat_model(store):
    chat = FakeChatModel(reply="She led Project Lumen.")

    result = answer("What did she lead?", FakeEmbedder(), store, chat, threshold=0.0, k=2)

    assert result.text == "She led Project Lumen."
    assert len(result.retrieved) == 2
    [messages] = chat.calls
    assert messages[1]["content"] == "What did she lead?"
    for r in result.retrieved:
        assert r.chunk.text in messages[0]["content"]
    scores = [r.score for r in result.retrieved]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.parametrize(
    "text",
    ["I don't have that information.", "No tengo esa información.", "  no tengo esa información "],
)
def test_refusals_are_recognised_in_both_languages(text):
    assert is_refusal(text)


def test_an_answer_that_mentions_missing_info_is_not_a_refusal():
    assert not is_refusal("No, she has never used Kubernetes in production.")


class StubStore:
    """Returns fixed search results, so each test controls the scores."""

    def __init__(self, *results: SearchResult):
        self.results = list(results)

    def search(self, query, query_vector, mode, k):
        return self.results[:k]


def _hit(file: str, section: str, score: float, text: str | None = None) -> SearchResult:
    text = text or f"{section} text"
    chunk = Chunk(
        id=f"{file}|{section}|{text}",
        content_hash="h",
        file=file,
        section=section,
        text=text,
        embed_text=text,
        metadata={},
    )
    return SearchResult(chunk, score)


def test_below_threshold_the_llm_is_never_called_and_the_refusal_is_in_the_question_language():
    chat = FakeChatModel()
    store = StubStore(_hit("profile.md", "Contact", 0.41))

    result = answer(
        "¿Cuál es su equipo de fútbol favorito?", FakeEmbedder(), store, chat, threshold=0.45
    )

    assert chat.calls == []
    assert result.refused
    assert result.text == refusal_for("es")
    assert result.citations == []
    assert result.retrieved == store.results


def test_only_chunks_above_the_threshold_reach_the_prompt():
    chat = FakeChatModel()
    store = StubStore(
        _hit("a.md", "Lumen", 0.65, "Led Lumen."),
        _hit("b.md", "Contact", 0.30, "Open to remote roles."),
    )

    answer("What did she lead?", FakeEmbedder(), store, chat, threshold=0.45)

    system = chat.calls[0][0]["content"]
    assert "Led Lumen." in system
    assert "Open to remote roles." not in system


def test_citations_come_from_metadata_deduplicated_and_ordered_by_score():
    store = StubStore(
        _hit("skills.md", "Cloud", 0.60),
        _hit("projects.md", "tinyledger", 0.55, "part 1"),
        _hit("projects.md", "tinyledger", 0.50, "part 2"),
        _hit("profile.md", "Contact", 0.20),
    )

    result = answer("q", FakeEmbedder(), store, FakeChatModel("An answer."), threshold=0.45)

    assert not result.refused
    assert result.citations == ["skills.md § Cloud", "projects.md § tinyledger"]


def test_when_the_llm_refuses_by_itself_there_are_no_citations():
    chat = FakeChatModel(reply="I don't have that information.")
    store = StubStore(_hit("profile.md", "Summary", 0.50))

    result = answer("Has she worked with JavaScript?", FakeEmbedder(), store, chat, threshold=0.45)

    assert result.refused
    assert result.citations == []
