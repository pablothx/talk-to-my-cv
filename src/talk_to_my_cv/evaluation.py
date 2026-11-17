"""Evaluation: retrieval metrics, per-question grading, threshold sweep and reports."""

import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal, NamedTuple, get_args

import yaml

from talk_to_my_cv.ingest import load_chunks
from talk_to_my_cv.language import detect_language
from talk_to_my_cv.rag import Answer
from talk_to_my_cv.store import SearchMode, UnsupportedSearchMode

QuestionType = Literal["answerable", "planted", "unanswerable", "negation"]


class Source(NamedTuple):
    file: str
    section: str

    def __str__(self) -> str:
        return f"{self.file} § {self.section}"


def hit_at_k(ranked: Sequence[Source], expected: Sequence[Source], k: int) -> float:
    """1.0 if any expected source is among the first k retrieved, else 0.0."""
    return 1.0 if set(ranked[:k]) & set(expected) else 0.0


def reciprocal_rank(ranked: Sequence[Source], expected: Sequence[Source]) -> float:
    """1/position of the first expected source retrieved (0.0 if none). Averaged, it is MRR."""
    for position, source in enumerate(ranked, start=1):
        if source in expected:
            return 1.0 / position
    return 0.0


def mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


@dataclass(frozen=True)
class Question:
    id: str
    type: QuestionType
    lang: Literal["es", "en"]
    question: str
    expected_sources: list[Source] = field(default_factory=list)
    expected_answer: str = ""
    must_contain: list[str] = field(default_factory=list)
    trap: str | None = None
    check_language: bool = False
    forbid_unsupported_no: bool = False

    @property
    def should_refuse(self) -> bool:
        return self.type == "unanswerable"


@dataclass(frozen=True)
class Grade:
    correct: bool
    reasons: list[str]
    hallucinated_no: bool = False
    language_ok: bool | None = None  # None = not checked for this question


NEGATIVE = re.compile(
    r"^\s*no\b|\b(never|nunca|did not|didn't|has not|hasn't|no ha|no usó|no utilizó)\b",
    re.IGNORECASE,
)


def asserts_no(text: str) -> bool:
    """Whether the reply answers in the negative ("No", "never", "nunca", "did not"...)."""
    return bool(NEGATIVE.search(text))


def grade(question: Question, answer: Answer) -> Grade:
    reasons: list[str] = []
    hallucinated_no = (
        question.forbid_unsupported_no and not answer.refused and asserts_no(answer.text)
    )
    if question.should_refuse:
        if not answer.refused:
            reasons.append("should have refused")
        if hallucinated_no:
            reasons.append("unsupported 'no': the KB is silent, only a refusal is correct")
    else:
        if answer.refused:
            reasons.append("refused an answerable question")
        if question.type == "negation" and not answer.refused and not asserts_no(answer.text):
            reasons.append("should have answered 'no'")
        text = answer.text.casefold()
        reasons += [
            f"missing {fact!r}" for fact in question.must_contain if fact.casefold() not in text
        ]

    language_ok = None
    if question.check_language and not answer.refused:
        language_ok = detect_language(answer.text) == question.lang
        if not language_ok:
            reasons.append(f"answer not in {question.lang}")

    return Grade(not reasons, reasons, hallucinated_no, language_ok)


MINIMUMS = {"answering": 8, "unanswerable": 6, "planted": 4}


def load_questions(path: Path, kb_dir: Path, minimums: bool = True) -> list[Question]:
    """Parse and validate the eval questions against the KB they are about."""
    sections = {Source(c.file, c.section) for c in load_chunks(kb_dir)}
    questions = []
    for raw in yaml.safe_load(path.read_text())["questions"]:
        sources = [Source(s["file"], s["section"]) for s in raw.pop("expected_sources", [])]
        question = Question(**raw, expected_sources=sources)
        if question.type not in get_args(QuestionType):
            raise ValueError(f"{question.id}: unknown type {question.type!r}")
        if not question.should_refuse and not sources:
            raise ValueError(f"{question.id}: answerable questions need expected_sources")
        for source in sources:
            if source not in sections:
                raise ValueError(f"{question.id}: {source} is not a chunk of {kb_dir}")
        questions.append(question)

    if minimums:
        counts = Counter(q.type for q in questions)
        found = {
            "answering": sum(n for t, n in counts.items() if t != "unanswerable"),
            "unanswerable": counts["unanswerable"],
            "planted": counts["planted"],
        }
        short = {k: f"{found[k]}/{n}" for k, n in MINIMUMS.items() if found[k] < n}
        if short:
            raise ValueError(f"{path.name} is below the minimums: {short}")
    return questions


# --- Running the eval -------------------------------------------------------


@dataclass(frozen=True)
class QuestionResult:
    question: Question
    answer: Answer
    grade: Grade
    ranked: list[Source]
    top_score: float | None


@dataclass
class EvalReport:
    store: str
    mode: SearchMode
    embed_model: str
    chat_model: str
    threshold: float
    k: int
    results: list[QuestionResult] = field(default_factory=list)
    skipped: str | None = None
    day: date = field(default_factory=date.today)

    def scored(self) -> list[QuestionResult]:
        """The questions that count for the targets: everything except deliberate traps."""
        return [r for r in self.results if not r.question.trap]

    def traps(self) -> list[QuestionResult]:
        return [r for r in self.results if r.question.trap]

    def metrics(self) -> dict[str, float | int | None]:
        scored = self.scored()
        answering = [r for r in scored if not r.question.should_refuse]
        checked_language = [r for r in self.results if r.grade.language_ok is not None]
        return {
            "questions": len(scored),
            f"hit@{self.k}": mean(
                [hit_at_k(r.ranked, r.question.expected_sources, self.k) for r in answering]
            ),
            "mrr": mean(
                [reciprocal_rank(r.ranked, r.question.expected_sources) for r in answering]
            ),
            "refusal_accuracy": mean(
                [float(r.answer.refused == r.question.should_refuse) for r in scored]
            ),
            "answer_accuracy": mean([float(r.grade.correct) for r in scored]),
            "hallucinated_no": sum(r.grade.hallucinated_no for r in self.results),
            "language_ok": mean([float(r.grade.language_ok) for r in checked_language]),
        }

    @property
    def name(self) -> str:
        return f"{self.day.isoformat()}_{self.store}_{self.mode}_{self.embed_model}"


def run_eval(
    questions: Sequence[Question],
    ask: Callable[[str], Answer],
    *,
    store: str,
    mode: SearchMode,
    embed_model: str,
    chat_model: str,
    threshold: float,
    k: int,
) -> EvalReport:
    report = EvalReport(store, mode, embed_model, chat_model, threshold, k)
    for question in questions:
        try:
            answer = ask(question.question)
        except UnsupportedSearchMode as error:
            report.skipped, report.results = str(error), []
            return report
        ranked = [Source(r.chunk.file, r.chunk.section) for r in answer.retrieved]
        top = max((r.score for r in answer.retrieved), default=None)
        report.results.append(
            QuestionResult(question, answer, grade(question, answer), ranked, top)
        )
    return report


# --- Reports ----------------------------------------------------------------


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def render_markdown(report: EvalReport) -> str:
    head = (
        f"# Eval {report.name}\n\n"
        f"- store: `{report.store}`, mode: `{report.mode}`, k: {report.k}\n"
        f"- embeddings: `{report.embed_model}`, threshold: {report.threshold:.2f}\n"
        f"- LLM: `{report.chat_model}`\n\n"
    )
    if report.skipped:
        return head + f"**Skipped:** {report.skipped}\n"
    lines = [head, "## Metrics (traps excluded)\n", "| Metric | Value |", "|---|---:|"]
    lines += [f"| {k} | {_fmt(v)} |" for k, v in report.metrics().items()]
    lines += [
        "",
        "## Questions\n",
        "| id | type | top-1 | refused | correct | notes |",
        "|---|---|---:|:-:|:-:|---|",
    ]
    for r in report.scored():
        lines.append(_row(r))
    lines += [
        "",
        "## Traps (known failures, reported apart)\n",
        "| id | trap | top-1 | refused | correct | notes |",
        "|---|---|---:|:-:|:-:|---|",
    ]
    for r in report.traps():
        lines.append(_row(r, r.question.trap or ""))
    return "\n".join(lines) + "\n"


def _row(r: QuestionResult, kind: str | None = None) -> str:
    top = _fmt(r.top_score)
    refused = "✓" if r.answer.refused else ""
    correct = "✓" if r.grade.correct else "✗"
    notes = "; ".join(r.grade.reasons)
    return (
        f"| {r.question.id} | {kind or r.question.type} | {top} | {refused} | {correct} | {notes} |"
    )


def write_report(report: EvalReport, out_dir: Path) -> tuple[Path, Path]:
    """Summary as Markdown + JSON (committed) and one raw JSONL line per question."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md, js = out_dir / f"{report.name}.md", out_dir / f"{report.name}.json"
    md.write_text(render_markdown(report))
    summary = {
        "name": report.name,
        "store": report.store,
        "mode": str(report.mode),
        "embed_model": report.embed_model,
        "chat_model": report.chat_model,
        "threshold": report.threshold,
        "k": report.k,
        "skipped": report.skipped,
        "metrics": None if report.skipped else report.metrics(),
    }
    js.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(exist_ok=True)
    with (raw_dir / f"{report.name}.jsonl").open("w") as raw:
        for r in report.results:
            row = {
                "id": r.question.id,
                "question": r.question.question,
                "answer": r.answer.text,
                "refused": r.answer.refused,
                "citations": r.answer.citations,
                "retrieved": [
                    [str(s), round(x.score, 4)]
                    for s, x in zip(r.ranked, r.answer.retrieved, strict=True)
                ],
                "grade": asdict(r.grade),
            }
            raw.write(json.dumps(row, ensure_ascii=False) + "\n")
    return md, js


# --- Threshold sweep (gate only, no LLM) --------------------------------------


@dataclass(frozen=True)
class SweepRow:
    threshold: float
    correct_refusals: float  # share of unanswerable questions the gate alone would refuse
    answerable_passing: float  # share of answering questions that get past the gate

    @property
    def gate_accuracy(self) -> float:
        return (self.correct_refusals + self.answerable_passing) / 2


def sweep(
    top_scores: Sequence[tuple[Question, float]], thresholds: Sequence[float]
) -> list[SweepRow]:
    scored = [(q, s) for q, s in top_scores if not q.trap]
    refuse = [s for q, s in scored if q.should_refuse]
    answer = [s for q, s in scored if not q.should_refuse]
    return [
        SweepRow(
            t,
            mean([float(s < t) for s in refuse]) or 0.0,
            mean([float(s >= t) for s in answer]) or 0.0,
        )
        for t in thresholds
    ]


def choose_threshold(rows: Sequence[SweepRow]) -> float:
    """Best gate-only accuracy; ties go to the lowest threshold.

    This is a candidate, not the answer: the gate ignores that the LLM can still refuse
    what gets through. Confirm candidates with the full eval (ADR-0009).
    """
    best = max(r.gate_accuracy for r in rows)
    return min(r.threshold for r in rows if r.gate_accuracy == best)
