from pathlib import Path

import pytest

from talk_to_my_cv.evaluation import load_questions

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "eval" / "questions.yaml"
KB = ROOT / "kb.example"


def test_shipped_questions_meet_the_minimums_and_cite_real_sections():
    questions = load_questions(QUESTIONS, KB)

    by_type = [q.type for q in questions]
    assert sum(t != "unanswerable" for t in by_type) >= 8
    assert by_type.count("unanswerable") >= 6
    assert by_type.count("planted") >= 4
    assert {q.lang for q in questions} == {"en", "es"}
    assert len({q.id for q in questions}) == len(questions)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "questions.yaml"
    path.write_text("questions:\n" + body)
    return path


def test_a_source_that_is_not_in_the_kb_fails_naming_the_question(tmp_path):
    path = _write(
        tmp_path,
        """
  - id: ghost
    type: answerable
    lang: en
    question: Where?
    expected_sources: [{file: profile.md, section: No such section}]
""",
    )

    with pytest.raises(ValueError, match="ghost.*profile.md § No such section"):
        load_questions(path, KB, minimums=False)


def test_answerable_questions_need_expected_sources(tmp_path):
    path = _write(
        tmp_path, "  - id: vague\n    type: answerable\n    lang: en\n    question: What\n"
    )

    with pytest.raises(ValueError, match="vague.*expected_sources"):
        load_questions(path, KB, minimums=False)
