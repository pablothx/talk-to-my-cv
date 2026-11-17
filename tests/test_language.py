import pytest

from talk_to_my_cv.language import detect_language
from talk_to_my_cv.rag import is_refusal, refusal_for


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("¿Usó Kubernetes?", "es"),
        ("¿Cuál es su equipo de fútbol favorito?", "es"),
        ("que tecnologias usa en el trabajo", "es"),
        ("Has she worked with JavaScript?", "en"),
        ("What is her favourite football team?", "en"),
        ("How much did Project Lumen speed up reconciliation?", "en"),
        ("Kubernetes?", None),
        ("AWS Lambda", None),
    ],
)
def test_detects_spanish_and_english_and_admits_when_unsure(question, expected):
    assert detect_language(question) == expected


def test_refusal_follows_the_language_and_is_bilingual_when_unsure():
    assert refusal_for("es") == "No tengo esa información."
    assert refusal_for("en") == "I don't have that information."
    assert refusal_for(None) == "No tengo esa información. / I don't have that information."


def test_bilingual_refusal_is_recognised():
    assert is_refusal(refusal_for(None))
