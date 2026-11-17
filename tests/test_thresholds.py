from pathlib import Path

import pytest

from talk_to_my_cv.embeddings import relevance_threshold


@pytest.fixture
def models_file(tmp_path: Path) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(
        "embedding_models:\n"
        "  bge-m3:\n    dimension: 1024\n    relevance_threshold: 0.45\n"
        "  bare-model:\n    dimension: 8\n"
    )
    return path


def test_threshold_is_read_per_embedding_model(models_file):
    assert relevance_threshold("bge-m3", env={}, models_file=models_file) == 0.45


def test_env_var_overrides_the_configured_threshold(models_file):
    env = {"RELEVANCE_THRESHOLD": "0.6"}

    assert relevance_threshold("bge-m3", env=env, models_file=models_file) == 0.6


def test_model_without_threshold_fails_pointing_to_the_config(models_file):
    with pytest.raises(ValueError, match="relevance_threshold.*models.yaml"):
        relevance_threshold("bare-model", env={}, models_file=models_file)


def test_the_shipped_config_has_a_threshold_for_the_default_model():
    assert 0 < relevance_threshold("bge-m3", env={}) < 1
