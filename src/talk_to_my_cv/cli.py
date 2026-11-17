"""Command-line entry points used by the Makefile."""

import argparse

from talk_to_my_cv.config import load_settings
from talk_to_my_cv.embeddings import build_embedder, cosine_similarity


def embed(text: str) -> None:
    embedder = build_embedder(load_settings())
    [vector] = embedder.embed([text])
    preview = ", ".join(f"{x:+.4f}" for x in vector[:8])
    print(f"model: {embedder.model}\ndimension: {len(vector)}\nfirst values: [{preview}, ...]")


def similarity(a: str, b: str) -> None:
    embedder = build_embedder(load_settings())
    va, vb = embedder.embed([a, b])
    print(f"{cosine_similarity(va, vb):.4f}  {a!r} ↔ {b!r}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="talk-to-my-cv")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("embed").add_argument("text")
    pair = commands.add_parser("similarity")
    pair.add_argument("a")
    pair.add_argument("b")
    args = parser.parse_args()
    if args.command == "embed":
        embed(args.text)
    else:
        similarity(args.a, args.b)


if __name__ == "__main__":
    main()
