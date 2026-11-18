import pytest
from fastapi.testclient import TestClient

from talk_to_my_cv.api import MAX_QUESTION_CHARS, create_app
from talk_to_my_cv.rag import REFUSALS, Answer


def _answer(text: str, refused: bool = False, citations: list[str] | None = None) -> Answer:
    return Answer(text, refused=refused, citations=citations or [], retrieved=[], context=[])


class FakeAsk:
    def __init__(self, reply: Answer):
        self.reply = reply
        self.questions: list[str] = []

    def __call__(self, question: str) -> Answer:
        self.questions.append(question)
        return self.reply


def _client(reply: Answer) -> tuple[TestClient, FakeAsk]:
    ask = FakeAsk(reply)
    return TestClient(create_app(ask)), ask


def test_the_api_answers_with_citations():
    client, ask = _client(_answer("She led Project Lumen.", citations=["exp.md § Lumen"]))

    response = client.post("/api/ask", json={"question": "What did she lead?"})

    assert response.status_code == 200
    assert response.json() == {
        "answer": "She led Project Lumen.",
        "refused": False,
        "citations": ["exp.md § Lumen"],
    }
    assert ask.questions == ["What did she lead?"]


def test_a_refusal_is_a_normal_answer_not_an_error():
    client, _ = _client(_answer(REFUSALS["en"], refused=True))

    response = client.post("/api/ask", json={"question": "What is her favourite team?"})

    assert response.status_code == 200
    assert response.json()["refused"] is True
    assert response.json()["citations"] == []


@pytest.mark.parametrize(
    "body",
    [{}, {"question": ""}, {"question": "   "}, {"question": "x" * (MAX_QUESTION_CHARS + 1)}],
)
def test_a_missing_empty_or_huge_question_is_rejected_before_any_model_call(body):
    client, ask = _client(_answer("unused"))

    response = client.post("/api/ask", json=body)

    assert response.status_code == 422
    assert ask.questions == []


def test_health():
    client, _ = _client(_answer("unused"))

    assert client.get("/health").json() == {"status": "ok"}


def test_the_page_has_a_form_and_a_strict_content_security_policy():
    client, _ = _client(_answer("unused"))

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<form method="post"' in response.text
    assert 'name="question"' in response.text
    assert "script-src 'none'" in response.headers["content-security-policy"]


def test_the_page_shows_the_answer_and_its_citations():
    client, _ = _client(_answer("She led Project Lumen.", citations=["exp.md § Lumen"]))

    response = client.post("/", data={"question": "What did she lead?"})

    assert response.status_code == 200
    assert "What did she lead?" in response.text
    assert "She led Project Lumen." in response.text
    assert "exp.md § Lumen" in response.text


def test_html_in_a_question_or_an_answer_is_shown_as_text_never_executed():
    # The answer echoes the question: a prompt injection could make the LLM write HTML.
    payload = '<script>alert(1)</script><img src=x onerror="alert(2)">'
    client, _ = _client(_answer(payload, citations=[f"cv.md § {payload}"]))

    response = client.post("/", data={"question": payload})

    assert "<script>alert(1)" not in response.text
    assert "<img src=x" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text


def test_an_empty_question_in_the_form_is_rejected_before_any_model_call():
    client, ask = _client(_answer("unused"))

    response = client.post("/", data={"question": "  "})

    assert response.status_code == 422
    assert ask.questions == []


class DownAsk:
    def __call__(self, question: str) -> Answer:
        raise ConnectionError("Failed to connect to Ollama.")


def test_a_model_server_that_is_down_is_a_503_with_a_hint_not_a_500():
    client = TestClient(create_app(DownAsk()))

    api = client.post("/api/ask", json={"question": "What is her tech stack?"})
    page = client.post("/", data={"question": "What is her tech stack?"})

    assert api.status_code == 503
    assert "OLLAMA_HOST" in api.json()["detail"]
    assert page.status_code == 503
    assert "OLLAMA_HOST" in page.text
