"""A CV as a PDF → KB Markdown, with fixed rules and no LLM: nothing can be invented.

- The first line is the person's name: the document title.
- An ALL-CAPS line ("PROFESSIONAL EXPERIENCE") opens a section (`##`).
- A line ending in a year range ("Senior Engineer, Acme (2021 – Present)") opens a
  subsection (`###`): one chunk per job, with the company in its heading path.
"""

import re
from pathlib import Path

from pypdf import PdfReader

YEAR_RANGE = re.compile(
    r"\b(19|20)\d{2}\s*[–—-]\s*((19|20)\d{2}|present|current|now|presente|actualidad|hoy)"
    r"\s*\)?\s*$",
    re.IGNORECASE,
)
MAX_HEADING_CHARS = 60


def _is_heading(line: str) -> bool:
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and line == line.upper() and len(line) <= MAX_HEADING_CHARS


def markdown_from_cv_text(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    title, rest = lines[0], lines[1:]
    out = [f"---\ntitle: {title}\n---\n# {title}\n"]
    for line in rest:
        if _is_heading(line):
            out.append(f"\n## {line.capitalize()}\n")
        elif YEAR_RANGE.search(line):
            out.append(f"\n### {line}\n")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def extract_pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
