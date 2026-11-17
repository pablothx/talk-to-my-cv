"""Command-line entry points used by the Makefile."""

import argparse
import sys
import time
from pathlib import Path

from talk_to_my_cv.chat_models import build_chat_model
from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder, cosine_similarity, relevance_threshold
from talk_to_my_cv.evaluation import (
    choose_threshold,
    load_questions,
    run_eval,
    sweep,
    write_report,
)
from talk_to_my_cv.ingest import EmbeddingModelMismatch
from talk_to_my_cv.ingest import ingest as run_ingest
from talk_to_my_cv.rag import Answer, answer
from talk_to_my_cv.store import PgVectorStore, SearchMode
from talk_to_my_cv.sweep_plot import plot_sweep


def embed(text: str) -> None:
    embedder = build_embedder(load_settings())
    [vector] = embedder.embed([text])
    preview = ", ".join(f"{x:+.4f}" for x in vector[:8])
    print(f"model: {embedder.model}\ndimension: {len(vector)}\nfirst values: [{preview}, ...]")


def similarity(a: str, b: str) -> None:
    embedder = build_embedder(load_settings())
    va, vb = embedder.embed([a, b])
    print(f"{cosine_similarity(va, vb):.4f}  {a!r} ↔ {b!r}")


def ingest(rebuild: bool) -> int:
    settings = load_settings()
    store = PgVectorStore(settings.database_url)
    try:
        report = run_ingest(settings.kb_dir, build_embedder(settings), store, rebuild=rebuild)
    except EmbeddingModelMismatch as error:
        print(f"✗ {error}")
        return 1
    print(
        f"{settings.kb_dir}: {report.added} added, {report.updated} updated, "
        f"{report.unchanged} unchanged, {report.deleted} deleted"
    )
    return 0


def _print_answer(result: Answer, threshold: float, debug: bool, seconds: float) -> None:
    if debug:
        print(f"── retrieved (threshold {threshold:.2f}; ✓ = sent to the LLM) ──")
        for r in result.retrieved:
            mark = "✓" if r in result.context else " "
            print(f"  {mark} {r.score:.3f}  {r.chunk.file} § {r.chunk.section}")
        llm = "LLM called" if result.context else "LLM not called"
        print(f"── answer ({seconds:.1f}s, {llm}) ──")
    print(result.text)
    if result.citations:
        print("\nSources:")
        for citation in result.citations:
            print(f"  - {citation}")


def ask(questions: list[str], debug: bool) -> int:
    """Answer each question; with no questions, read them interactively (REPL)."""
    settings = load_settings()
    embedder, chat = build_embedder(settings), build_chat_model(settings)
    store = PgVectorStore(settings.database_url)
    threshold = relevance_threshold(settings.embed_model)
    interactive = not questions
    if interactive:
        print(
            f"Chatting about {settings.kb_dir} with {settings.llm_provider}:"
            f"{settings.chat_model}. Empty line or Ctrl-D to quit."
        )
    while True:
        if interactive:
            try:
                question = input("\n> ").strip()
            except EOFError:
                break
            if not question:
                break
        elif questions:
            question = questions.pop(0)
        else:
            break
        start = time.perf_counter()
        result = answer(question, embedder, store, chat, threshold=threshold)
        _print_answer(result, threshold, debug, time.perf_counter() - start)
    return 0


ROOT = Path(__file__).resolve().parents[2]
EVAL_KB = ROOT / "kb.example"
QUESTIONS = ROOT / "eval" / "questions.yaml"
RESULTS = ROOT / "eval" / "results"
STORES = {"pgvector": lambda settings: PgVectorStore(settings.database_url, schema="eval")}


def _eval_setup(store_name: str):
    """The eval always runs against kb.example/, in its own schema, whatever KB_DIR says."""
    settings = load_settings()
    if store_name not in STORES:
        raise SystemExit(f"unknown STORE {store_name!r}; available: {', '.join(STORES)}")
    store = STORES[store_name](settings)
    embedder = build_embedder(settings)
    run_ingest(EVAL_KB, embedder, store)
    return settings, store, embedder


def evaluate(store_name: str, mode: str, threshold: float | None) -> int:
    settings, store, embedder = _eval_setup(store_name)
    chat = build_chat_model(settings)
    threshold = threshold if threshold is not None else relevance_threshold(settings.embed_model)
    questions = load_questions(QUESTIONS, EVAL_KB)
    search_mode = SearchMode(mode)

    def ask_one(question: str) -> Answer:
        print(f"  · {question}", flush=True)
        return answer(question, embedder, store, chat, threshold=threshold, mode=search_mode)

    report = run_eval(
        questions,
        ask_one,
        store=store_name,
        mode=search_mode,
        embed_model=settings.embed_model,
        chat_model=settings.chat_model,
        threshold=threshold,
        k=5,
    )
    md, js = write_report(report, RESULTS)
    print(f"\n{md.read_text()}\nwritten: {md.relative_to(ROOT)}, {js.relative_to(ROOT)}")
    return 0


def evaluate_sweep(store_name: str) -> int:
    settings, store, embedder = _eval_setup(store_name)
    questions = load_questions(QUESTIONS, EVAL_KB)
    vectors = embedder.embed([q.question for q in questions])
    top_scores = []
    for question, vector in zip(questions, vectors, strict=True):
        [top] = store.search(question.question, vector, mode=SearchMode.VECTOR, k=1)
        top_scores.append((question, top.score))
    rows = sweep(top_scores, thresholds=[round(0.35 + i / 100, 2) for i in range(31)])
    chosen = choose_threshold(rows)

    print(f"{'id':22} {'type':13} top-1")
    for question, score in sorted(top_scores, key=lambda x: x[1], reverse=True):
        trap = "  (trap)" if question.trap else ""
        print(f"{question.id:22} {question.type:13} {score:.3f}{trap}")
    print("\nthreshold  refused  passing  gate accuracy")
    for r in rows:
        mark = "  ← gate-only best" if r.threshold == chosen else ""
        print(
            f"  {r.threshold:.2f}     {r.correct_refusals:5.0%}   {r.answerable_passing:5.0%}"
            f"   {r.gate_accuracy:5.0%}{mark}"
        )
    configured = relevance_threshold(settings.embed_model)
    png = plot_sweep(
        rows,
        chosen,
        configured,
        settings.embed_model,
        RESULTS / f"threshold-sweep_{settings.embed_model}.png",
    )
    print(f"\ngate-only best: {chosen:.2f}  ·  configured: {configured:.2f}")
    print("The gate ignores that the LLM can still refuse: confirm candidates with")
    print("`make eval THRESHOLD=...` and set the winner in config/models.yaml (ADR-0009).")
    print(f"written: {png.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="talk-to-my-cv")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("embed").add_argument("text")
    pair = commands.add_parser("similarity")
    pair.add_argument("a")
    pair.add_argument("b")
    commands.add_parser("ingest").add_argument("--rebuild", action="store_true")
    chat = commands.add_parser("chat")
    chat.add_argument("question", nargs="*", help="ask once and exit; omit for a REPL")
    chat.add_argument("--debug", action="store_true", help="show retrieved chunks and scores")
    run = commands.add_parser("eval")
    run.add_argument("--store", default="pgvector")
    run.add_argument("--mode", default="vector", choices=[m.value for m in SearchMode])
    run.add_argument("--threshold", type=float, default=None)
    commands.add_parser("eval-sweep").add_argument("--store", default="pgvector")
    args = parser.parse_args()
    if args.command == "embed":
        embed(args.text)
    elif args.command == "similarity":
        similarity(args.a, args.b)
    elif args.command == "ingest":
        return ingest(args.rebuild)
    elif args.command == "eval":
        return evaluate(args.store, args.mode, args.threshold)
    elif args.command == "eval-sweep":
        return evaluate_sweep(args.store)
    else:
        return ask([" ".join(args.question)] if args.question else [], args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
