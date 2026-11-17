"""`make eval` end to end: real store, real models, reports written to a temp dir."""

import json

import pytest

from talk_to_my_cv import cli

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def results_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "RESULTS", tmp_path)
    monkeypatch.setattr(cli, "ROOT", tmp_path.parent)
    return tmp_path


def test_vector_eval_writes_markdown_and_json_with_every_metric(results_in_tmp):
    assert cli.evaluate("pgvector", "vector", threshold=None) == 0

    [summary] = results_in_tmp.glob("*_pgvector_vector_bge-m3.json")
    metrics = json.loads(summary.read_text())["metrics"]
    for name in ("hit@5", "mrr", "refusal_accuracy", "answer_accuracy"):
        assert metrics[name] is not None
    assert summary.with_suffix(".md").exists()


def test_hybrid_on_pgvector_is_reported_as_skipped(results_in_tmp):
    assert cli.evaluate("pgvector", "hybrid", threshold=None) == 0

    [summary] = results_in_tmp.glob("*_pgvector_hybrid_bge-m3.json")
    data = json.loads(summary.read_text())
    assert "does not support 'hybrid'" in data["skipped"]
    assert data["metrics"] is None
