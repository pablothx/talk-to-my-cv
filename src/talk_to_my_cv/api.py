"""HTTP API and a minimal web page to chat with the KB (step 8)."""

from collections.abc import Callable
from html import escape
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, StringConstraints

from talk_to_my_cv.config import load_settings
from talk_to_my_cv.engines import build_ask
from talk_to_my_cv.rag import Answer

MAX_QUESTION_CHARS = 500

Ask = Callable[[str], Answer]
Question = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_CHARS)
]


class AskRequest(BaseModel):
    question: Question


class AskResponse(BaseModel):
    answer: str
    refused: bool
    citations: list[str]


# No JavaScript at all, and the browser is told so: even if escaping failed somewhere,
# an injected <script> would not run.
CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; script-src 'none'"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Talk to my CV</title>
<style>
  :root {{ --bg: #fcfcfb; --ink: #0b0b0b; --muted: #52514e; --line: #e1e0d9; --accent: #2a78d6;
           --on-accent: #ffffff; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #141413; --ink: #f0efea; --muted: #a8a69f; --line: #34332f; --accent: #6aa6ec;
             --on-accent: #0b0b0b; }}
  }}
  body {{ background: var(--bg); color: var(--ink); font: 16px/1.5 system-ui, sans-serif;
         max-width: 42rem; margin: 2rem auto; padding: 0 1rem; }}
  textarea {{ width: 100%; box-sizing: border-box; font: inherit; padding: .5rem;
             background: var(--bg); color: var(--ink); border: 1px solid var(--line); }}
  button {{ font: inherit; padding: .4rem 1rem; margin-top: .5rem; background: var(--accent);
           color: var(--on-accent); border: 0; border-radius: 4px; cursor: pointer; }}
  .muted {{ color: var(--muted); font-size: .9rem; }}
  .answer {{ white-space: pre-wrap; border-left: 3px solid var(--accent); padding-left: 1rem; }}
  .refused {{ border-left-color: var(--line); color: var(--muted); }}
</style>
</head>
<body>
<h1>Talk to my CV</h1>
<p class="muted">Answers come only from the CV documents, with their sources.
On a CPU-only machine an answer takes 10–30 seconds.</p>
<form method="post" action="/">
  <textarea name="question" rows="3" maxlength="{max_chars}" required
    placeholder="What is her tech stack?">{question}</textarea>
  <button type="submit">Ask</button>
</form>
{result}
</body>
</html>
"""


def render_page(question: str = "", result: Answer | None = None, error: str = "") -> str:
    """Every dynamic value goes through html.escape: questions and answers are text, not HTML."""
    block = f'<p class="answer refused">{escape(error)}</p>\n' if error else ""
    if result is not None:
        css = "answer refused" if result.refused else "answer"
        block = f'<h2>Answer</h2>\n<p class="{css}">{escape(result.text)}</p>\n'
        if result.citations:
            items = "".join(f"<li>{escape(c)}</li>" for c in result.citations)
            block += f'<h3>Sources</h3>\n<ul class="muted">{items}</ul>\n'
    return PAGE.format(max_chars=MAX_QUESTION_CHARS, question=escape(question), result=block)


def _html(content: str) -> HTMLResponse:
    return HTMLResponse(content, headers={"Content-Security-Policy": CSP})


MODEL_SERVER_DOWN = (
    "Can't reach the model server. Is Ollama running, and does OLLAMA_HOST point to it? "
    "From a container on Linux, Ollama must listen on more than 127.0.0.1 (see lesson 8)."
)


def create_app(ask: Ask) -> FastAPI:
    """The app gets the question → Answer function injected: fakes in tests, models in prod."""
    app = FastAPI(title="talk-to-my-cv")

    @app.exception_handler(ConnectionError)
    def model_server_down(request: Request, error: ConnectionError):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": MODEL_SERVER_DOWN}, status_code=503)
        page = render_page(error=MODEL_SERVER_DOWN)
        return HTMLResponse(page, status_code=503, headers={"Content-Security-Policy": CSP})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/ask")
    def api_ask(request: AskRequest) -> AskResponse:
        result = ask(request.question)
        return AskResponse(answer=result.text, refused=result.refused, citations=result.citations)

    @app.get("/", response_class=HTMLResponse)
    def page() -> HTMLResponse:
        return _html(render_page())

    @app.post("/", response_class=HTMLResponse)
    def page_ask(question: Annotated[Question, Form()]) -> HTMLResponse:
        return _html(render_page(question, ask(question)))

    return app


def app_from_settings() -> FastAPI:
    """Entry point for uvicorn (`--factory`): real models, store and engine from `.env`."""
    return create_app(build_ask(load_settings()))
