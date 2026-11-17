import json

import pytest

from talk_to_my_cv.chunking import Chunk
from talk_to_my_cv.evaluation import (
    Question,
    Source,
    choose_threshold,
    run_eval,
    sweep,
    write_report,
)
from talk_to_my_cv.rag import Answer, refusal_for
from talk_to_my_cv.store import SearchMode, SearchResult, UnsupportedSearchMode

LUMEN = Source("exp.md", "Lumen")
OTHER = Source("profile.md", "Contact")


def _result(source: Source, score: float) -> SearchResult:
    chunk = Chunk(
        id=str(source),
        content_hash="h",
        file=source.file,
        section=source.section,
        text="t",
        embed_text="t",
        metadata={},
    )
    return SearchResult(chunk, score)


QUESTIONS = [
    Question(
        id="lumen",
        type="planted",
        lang="en",
        question="Lumen?",
        expected_sources=[LUMEN],
        must_contain=["14 minutes"],
    ),
    Question(id="football", type="unanswerable", lang="en", question="Football?"),
    Question(
        id="js",
        type="unanswerable",
        lang="en",
        question="JavaScript?",
        trap="embedding-false-positive",
        forbid_unsupported_no=True,
    ),
]

REPLIES = {
    "Lumen?": Answer(
        "14 minutes.",
        refused=False,
        citations=[str(LUMEN)],
        retrieved=[_result(OTHER, 0.5), _result(LUMEN, 0.6)],
        context=[],
    ),
    "Football?": Answer(
        refusal_for("en"), refused=True, citations=[], retrieved=[_result(OTHER, 0.41)], context=[]
    ),
    "JavaScript?": Answer(
        "No", refused=False, citations=[str(OTHER)], retrieved=[_result(OTHER, 0.499)], context=[]
    ),
}


def _run(ask=REPLIES.__getitem__):
    return run_eval(
        QUESTIONS,
        ask,
        store="memory",
        mode=SearchMode.VECTOR,
        embed_model="fake",
        chat_model="fake",
        threshold=0.45,
        k=5,
    )


def test_metrics_exclude_traps_and_traps_are_reported_apart():
    report = _run()

    metrics = report.metrics()
    assert metrics["hit@5"] == 1.0
    assert metrics["mrr"] == 0.5
    assert metrics["refusal_accuracy"] == 1.0
    assert metrics["answer_accuracy"] == 1.0
    assert metrics["questions"] == 2
    [trap] = report.traps()
    assert trap.question.id == "js"
    assert trap.grade.hallucinated_no


def test_unsupported_mode_is_a_skip_not_a_failure():
    def ask(question):
        raise UnsupportedSearchMode("PgVectorStore", SearchMode.HYBRID)

    report = _run(ask)

    assert report.skipped
    assert report.results == []


def test_report_is_written_as_markdown_json_and_raw(tmp_path):
    report = _run()

    md, js = write_report(report, tmp_path)

    assert md.name.endswith("_memory_vector_fake.md")
    assert js.with_suffix(".md") == md
    data = json.loads(js.read_text())
    assert data["metrics"]["refusal_accuracy"] == 1.0
    assert "hit@5" in md.read_text()
    assert "js" in md.read_text()
    assert len(list((tmp_path / "raw").glob("*.jsonl"))) == 1


def test_sweep_measures_the_gate_alone_and_the_lowest_best_threshold_wins():
    scores = [(QUESTIONS[0], 0.60), (QUESTIONS[1], 0.41), (QUESTIONS[2], 0.499)]

    rows = sweep(scores, thresholds=[0.40, 0.45, 0.50, 0.55, 0.65])

    by_t = {r.threshold: r for r in rows}
    assert by_t[0.40].correct_refusals == 0.0 and by_t[0.40].answerable_passing == 1.0
    assert by_t[0.45].correct_refusals == 1.0 and by_t[0.45].answerable_passing == 1.0
    assert by_t[0.65].answerable_passing == 0.0
    assert choose_threshold(rows) == pytest.approx(0.45)
