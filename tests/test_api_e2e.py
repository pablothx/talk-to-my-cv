"""The API container against native Ollama and the ingested KB (`make api-up` first)."""

import os

import httpx
import pytest

pytestmark = pytest.mark.e2e

BASE = f"http://localhost:{os.environ.get('API_PORT', '8000')}"


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=BASE, timeout=180) as client:
        yield client


def test_the_container_answers_a_planted_fact_with_its_citation(api):
    response = api.post(
        "/api/ask", json={"question": "How much did Project Lumen speed up reconciliation?"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "14 minutes" in body["answer"]
    assert any("Project Lumen" in c for c in body["citations"])


def test_the_page_escapes_html_coming_back_from_the_model(api):
    # The off-topic question is refused, but the page still echoes it: escaped.
    response = api.post("/", data={"question": "<script>alert(1)</script>"})

    assert response.status_code == 200
    assert "<script>alert(1)" not in response.text
    assert "&lt;script&gt;" in response.text
    assert "script-src 'none'" in response.headers["content-security-policy"]
