"""Command-line entry points used by the Makefile."""

import argparse
import sys
import time

from talk_to_my_cv.chat_models import build_chat_model
from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder, cosine_similarity
from talk_to_my_cv.ingest import EmbeddingModelMismatch
from talk_to_my_cv.ingest import ingest as run_ingest
from talk_to_my_cv.rag import Answer, answer
from talk_to_my_cv.store import PgVectorStore


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


def _print_answer(result: Answer, debug: bool, seconds: float) -> None:
    if debug:
        print("── retrieved context ──")
        for r in result.retrieved:
            print(f"  {r.score:.3f}  {r.chunk.file} § {r.chunk.section}")
        print(f"── answer ({seconds:.1f}s) ──")
    print(result.text)


def ask(questions: list[str], debug: bool) -> int:
    """Answer each question; with no questions, read them interactively (REPL)."""
    settings = load_settings()
    embedder, chat = build_embedder(settings), build_chat_model(settings)
    store = PgVectorStore(settings.database_url)
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
        result = answer(question, embedder, store, chat)
        _print_answer(result, debug, time.perf_counter() - start)
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
    args = parser.parse_args()
    if args.command == "embed":
        embed(args.text)
    elif args.command == "similarity":
        similarity(args.a, args.b)
    elif args.command == "ingest":
        return ingest(args.rebuild)
    else:
        return ask([" ".join(args.question)] if args.question else [], args.debug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
