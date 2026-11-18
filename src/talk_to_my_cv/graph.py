"""The RAG flow as a LangGraph graph, with an LLM verification step (step 7, ADR-0009).

[reformulate] → retrieve → gate ─┬─ nothing above the threshold ──────────────→ refuse
                 └─ verify ─┬─ "NO" ──────────────────────────→ refuse
                            └─ "YES" or unclear → generate → answer with citations
"""

import re
import unicodedata
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from talk_to_my_cv.embeddings import Embedder
from talk_to_my_cv.language import detect_language
from talk_to_my_cv.rag import (
    Answer,
    ChatModel,
    build_prompt,
    cite,
    format_context,
    is_refusal,
    refusal_for,
)
from talk_to_my_cv.store import SearchMode, SearchResult, VectorStore

REFORMULATE_PROMPT = """\
Rewrite this question about a person's CV as a short English keyword search query. \
Keep names, technologies and numbers as they are. Reply with only the keywords.

QUESTION: {question}"""

EXTRACT_PROMPT = """\
List the specific names a question about a CV asks about: technologies, tools, \
companies, products, projects or certifications, written in English as a CV would write them.
Category words are not names: "technologies", "languages", "certifications", "skills", \
"tools", "frameworks" -> NONE.
If the question names nothing specific, reply NONE.
Reply with only the names, separated by commas, or NONE.

Examples:
Does she know Rust? -> Rust
¿Trabajó en Acme Corp con Terraform? -> Acme Corp, Terraform
What frameworks has she used? -> NONE
¿Dónde estudió? -> NONE
Is she a good leader? -> NONE"""

MAX_WORDS_PER_NAME = 4


def parse_terms(reply: str) -> list[str]:
    """The extractor's names; [] for NONE or for anything that doesn't look like a list of names."""
    terms = [t.strip(" \t\n*_`'\".") for t in reply.split(",")]
    terms = [t for t in terms if t and t.casefold() != "none"]
    if any(len(t.split()) > MAX_WORDS_PER_NAME for t in terms):
        return []  # a chatty reply would make every "term" missing and refuse: fail open
    return terms


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(c for c in decomposed if not unicodedata.combining(c)).split())


def mentions(term: str, text: str) -> bool:
    """Whole-word, case- and accent-insensitive: "Java" is not in "JavaScript"."""
    pattern = r"(?<!\w)" + r"\s+".join(map(re.escape, _fold(term).split())) + r"(?!\w)"
    return re.search(pattern, _fold(text)) is not None


class State(TypedDict, total=False):
    question: str
    query: str | None
    retrieved: list[SearchResult]
    context: list[SearchResult]
    verified: bool | None
    answer: Answer


def build_graph(
    embedder: Embedder,
    store: VectorStore,
    chat: ChatModel,
    threshold: float,
    k: int = 5,
    mode: SearchMode = SearchMode.VECTOR,
):
    def reformulate(state: State) -> State:
        prompt = REFORMULATE_PROMPT.format(question=state["question"])
        query = chat.complete([{"role": "user", "content": prompt}]).strip()
        return {"query": query or None}

    def retrieve(state: State) -> State:
        # The vector always comes from the original question, so the threshold calibrated
        # in step 5 still holds; the reformulated query only feeds keyword search (BM25).
        [vector] = embedder.embed([state["question"]])
        text_query = state.get("query") or state["question"]
        retrieved = store.search(text_query, vector, mode=mode, k=k)
        return {"retrieved": retrieved, "context": [r for r in retrieved if r.score >= threshold]}

    def verify(state: State) -> State:
        reply = chat.complete(
            [
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": state["question"]},
            ]
        )
        terms = parse_terms(reply)
        if not terms:
            return {"verified": None}  # nothing specific to check: the answer prompt decides
        context = format_context(state["context"])
        # Any one name is enough: "Kafka and Flink?" can still be half answered.
        return {"verified": any(mentions(t, context) for t in terms)}

    def generate(state: State) -> State:
        text = chat.complete(build_prompt(state["question"], state["context"]))
        return {"answer": _answer(state, text, refused=is_refusal(text))}

    def refuse(state: State) -> State:
        text = refusal_for(detect_language(state["question"]))
        return {"answer": _answer(state, text, refused=True)}

    graph = StateGraph(State)
    for name, node in [
        ("reformulate", reformulate),
        ("retrieve", retrieve),
        ("verify", verify),
        ("generate", generate),
        ("refuse", refuse),
    ]:
        graph.add_node(name, node)
    # BM25 can't match a Spanish question against an English KB; vectors don't need help.
    graph.add_edge(START, "retrieve" if mode == SearchMode.VECTOR else "reformulate")
    graph.add_edge("reformulate", "retrieve")
    # The relevance gate (ADR-0006): below the threshold, the LLM is never called.
    graph.add_conditional_edges(
        "retrieve", lambda s: "verify" if s["context"] else "refuse", ["verify", "refuse"]
    )
    # Only a missing name refuses; None (nothing to check) leaves it to the answer prompt.
    graph.add_conditional_edges(
        "verify",
        lambda s: "refuse" if s["verified"] is False else "generate",
        ["generate", "refuse"],
    )
    graph.add_edge("generate", END)
    graph.add_edge("refuse", END)
    return graph.compile()


def _answer(state: State, text: str, refused: bool) -> Answer:
    context = state.get("context", [])
    return Answer(
        text,
        refused=refused,
        citations=[] if refused else cite(context),
        retrieved=state.get("retrieved", []),
        context=context,
        verified=state.get("verified"),
        query=state.get("query"),
    )


def answer_with_graph(
    question: str,
    embedder: Embedder,
    store: VectorStore,
    chat: ChatModel,
    threshold: float,
    k: int = 5,
    mode: SearchMode = SearchMode.VECTOR,
) -> Answer:
    graph = build_graph(embedder, store, chat, threshold, k, mode)
    return graph.invoke({"question": question})["answer"]
