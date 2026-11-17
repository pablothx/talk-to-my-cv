"""Split a Markdown KB document into citable chunks."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

import yaml

HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
MAX_CHARS = 1500


@dataclass(frozen=True)
class Chunk:
    id: str
    content_hash: str
    file: str
    section: str
    text: str
    embed_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER.match(markdown)
    if not match:
        return {}, markdown
    raw = yaml.safe_load(match.group(1)) or {}
    # Round-trip through JSON so dates and other YAML types become storable strings.
    return json.loads(json.dumps(raw, default=str)), markdown[match.end() :]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _pack_paragraphs(text: str, limit: int = MAX_CHARS) -> list[str]:
    """Greedily pack whole paragraphs into pieces of at most `limit` chars."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for paragraph in re.split(r"\n\s*\n", text):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > limit:
            pieces.append(current)
            current = paragraph
        else:
            current = candidate
    pieces.append(current)
    return pieces


def chunk_document(path: str, markdown: str) -> list[Chunk]:
    metadata, body = _split_frontmatter(markdown)
    title = metadata.get("title") or PurePosixPath(path).stem
    sections: list[tuple[str, list[str]]] = [(title, [])]
    current_h2: str | None = None

    for line in body.splitlines():
        match = HEADING.match(line)
        if not match:
            sections[-1][1].append(line)
        elif len(match.group(1)) == 1:
            title = metadata.get("title") or match.group(2)
            sections[0] = (title, sections[0][1])
        elif len(match.group(1)) == 2:
            current_h2 = match.group(2)
            sections.append((current_h2, []))
        else:
            path_ = f"{current_h2} > {match.group(2)}" if current_h2 else match.group(2)
            sections.append((path_, []))

    chunks = []
    for section, lines in sections:
        text = "\n".join(lines).strip()
        if not text:
            continue
        breadcrumb = title if section == title else f"{title} > {section}"
        for index, piece in enumerate(_pack_paragraphs(text)):
            embed_text = f"{breadcrumb}\n\n{piece}"
            chunks.append(
                Chunk(
                    id=_sha(f"{path}|{section}|{index}"),
                    content_hash=_sha(embed_text + json.dumps(metadata, sort_keys=True)),
                    file=path,
                    section=section,
                    text=piece,
                    embed_text=embed_text,
                    metadata=metadata,
                )
            )
    return chunks
