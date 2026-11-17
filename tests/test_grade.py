from talk_to_my_cv.evaluation import Question, Source, asserts_no, grade
from talk_to_my_cv.rag import Answer, refusal_for

INFRA = Source("experience/northwind-payments.md", "Senior Backend Engineer > Infrastructure")


def _q(type_: str, lang: str = "en", **extra) -> Question:
    return Question(id="q", type=type_, lang=lang, question="?", **extra)


def _answer(text: str, refused: bool = False) -> Answer:
    return Answer(text, refused=refused, citations=[], retrieved=[], context=[])


def test_unanswerable_is_correct_only_when_refused():
    assert grade(_q("unanswerable"), _answer(refusal_for("en"), refused=True)).correct
    assert not grade(_q("unanswerable"), _answer("She likes Boca.")).correct


def test_answerable_needs_no_refusal_and_every_key_fact_case_insensitive():
    question = _q("planted", must_contain=["9 hours", "14 minutes"])

    assert grade(question, _answer("From 9 hours to 14 Minutes.")).correct
    missing = grade(question, _answer("It got much faster."))
    assert not missing.correct
    assert "missing '9 hours'" in missing.reasons
    assert not grade(question, _answer(refusal_for("en"), refused=True)).correct


def test_negation_must_answer_no_without_refusing():
    question = _q("negation", lang="es", expected_sources=[INFRA])

    assert grade(question, _answer("No, nunca usó Kubernetes en producción.")).correct
    assert not grade(question, _answer("Sí, usó Kubernetes.")).correct
    assert not grade(question, _answer(refusal_for("es"), refused=True)).correct


def test_unsupported_no_is_flagged_as_hallucination():
    question = _q("unanswerable", forbid_unsupported_no=True)

    result = grade(question, _answer("No"))

    assert not result.correct
    assert result.hallucinated_no
    assert not grade(question, _answer(refusal_for("en"), refused=True)).hallucinated_no


def test_language_rule_is_checked_only_when_asked():
    checked = _q("negation", lang="es", check_language=True)
    unchecked = _q("negation", lang="es")
    english = _answer("No, she has never used Kubernetes in production.")

    result = grade(checked, english)
    assert not result.correct
    assert result.language_ok is False
    assert grade(unchecked, english).language_ok is None
    assert grade(unchecked, english).correct


def test_asserts_no_recognises_negative_answers_in_both_languages():
    for text in ("No", "No, she has never used it.", "Nunca lo usó.", "She did not use it."):
        assert asserts_no(text), text
    for text in ("Yes, with HubSpot.", "Sí, integró HubSpot.", "Notably, she led Lumen."):
        assert not asserts_no(text), text
