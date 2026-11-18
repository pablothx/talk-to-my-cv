from fakes import FakeEmbedder, ScriptedChatModel

from talk_to_my_cv.chunking import Chunk
from talk_to_my_cv.graph import answer_with_graph
from talk_to_my_cv.rag import REFUSALS
from talk_to_my_cv.store import SearchMode, SearchResult


class StubStore:
    """Fixed results; records the text query each search received."""

    supported_modes = frozenset(SearchMode)

    def __init__(self, *results: SearchResult):
        self.results = list(results)
        self.queries: list[str] = []

    def search(self, query, query_vector, mode, k):
        self.queries.append(query)
        return self.results[:k]


def _hit(section: str, score: float) -> SearchResult:
    text = f"{section} details."
    chunk = Chunk(f"id-{section}", "h", "cv.md", section, text, text, {})
    return SearchResult(chunk, score)


def test_below_the_threshold_it_refuses_without_calling_the_llm():
    chat = ScriptedChatModel()

    result = answer_with_graph(
        "¿Cuánto cobra?", FakeEmbedder(), StubStore(_hit("Lumen", 0.30)), chat, threshold=0.42
    )

    assert result.refused
    assert result.text == REFUSALS["es"]
    assert chat.calls == []


def test_a_named_term_missing_from_the_context_refuses_without_writing_an_answer():
    chat = ScriptedChatModel("JavaScript")

    result = answer_with_graph(
        "Has she worked with JavaScript?",
        FakeEmbedder(),
        StubStore(_hit("Languages", 0.50)),
        chat,
        threshold=0.42,
    )

    assert result.refused
    assert result.text == REFUSALS["en"]
    assert result.verified is False
    assert len(chat.calls) == 1
    assert "Has she worked with JavaScript?" in chat.calls[0][-1]["content"]


def test_a_named_term_found_in_the_context_answers_with_citations():
    chat = ScriptedChatModel("Lumen", "She led Project Lumen.")

    result = answer_with_graph(
        "What did she lead?", FakeEmbedder(), StubStore(_hit("Lumen", 0.60)), chat, threshold=0.42
    )

    assert not result.refused
    assert result.text == "She led Project Lumen."
    assert result.citations == ["cv.md § Lumen"]
    assert result.verified is True
    assert len(chat.calls) == 2


def test_a_general_question_lets_the_answer_step_decide():
    chat = ScriptedChatModel("NONE", "I don't have that information.")

    result = answer_with_graph(
        "What did she lead?", FakeEmbedder(), StubStore(_hit("Lumen", 0.60)), chat, threshold=0.42
    )

    assert result.verified is None
    assert len(chat.calls) == 2
    assert result.refused
    assert result.citations == []


def test_in_hybrid_mode_the_keyword_query_is_reformulated_but_the_vector_is_not():
    embedder, store = FakeEmbedder(), StubStore(_hit("Languages", 0.60))
    chat = ScriptedChatModel("languages spoken", "NONE", "Spanish and English.")

    result = answer_with_graph(
        "¿Qué idiomas habla?", embedder, store, chat, threshold=0.42, mode=SearchMode.HYBRID
    )

    assert store.queries == ["languages spoken"]
    assert embedder.embedded == ["¿Qué idiomas habla?"]
    assert result.query == "languages spoken"
    assert "¿Qué idiomas habla?" in chat.calls[0][-1]["content"]
    assert result.text == "Spanish and English."


def test_an_empty_reformulation_falls_back_to_the_question():
    store = StubStore(_hit("Languages", 0.60))
    chat = ScriptedChatModel("  ", "NONE", "Spanish and English.")

    answer_with_graph(
        "¿Qué idiomas habla?", FakeEmbedder(), store, chat, threshold=0.42, mode=SearchMode.KEYWORD
    )

    assert store.queries == ["¿Qué idiomas habla?"]


def test_in_vector_mode_there_is_nothing_to_reformulate():
    store = StubStore(_hit("Lumen", 0.60))
    chat = ScriptedChatModel("NONE", "She led Project Lumen.")

    result = answer_with_graph("What did she lead?", FakeEmbedder(), store, chat, threshold=0.42)

    assert store.queries == ["What did she lead?"]
    assert result.query is None
    assert len(chat.calls) == 2
