from pathlib import Path

import pytest
from fakes import FakeEmbedder

from talk_to_my_cv.ingest import EmbeddingModelMismatch, ingest
from talk_to_my_cv.store import InMemoryStore

PROFILE = "---\ntitle: Ada\n---\n## Summary\n\nBackend engineer.\n\n## Languages\n\nSpanish.\n"
SKILLS = "---\ntitle: Skills\n---\n## Languages\n\nJava 21.\n"


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    (tmp_path / "experience").mkdir()
    (tmp_path / "profile.md").write_text(PROFILE)
    (tmp_path / "experience" / "skills.md").write_text(SKILLS)
    return tmp_path


def test_first_run_adds_every_chunk_and_second_run_changes_nothing(kb):
    store, embedder = InMemoryStore(), FakeEmbedder()

    first = ingest(kb, embedder, store)
    embedder.embedded.clear()
    second = ingest(kb, embedder, store)

    assert first.added == 3
    assert (second.added, second.updated, second.deleted, second.unchanged) == (0, 0, 0, 3)
    assert embedder.embedded == []
    assert {"profile.md", "experience/skills.md"} == {
        r.chunk.file for r in store.search("q", [1.0] * 8, mode="vector", k=10)
    }


def test_editing_one_section_re_embeds_only_that_chunk(kb):
    store, embedder = InMemoryStore(), FakeEmbedder()
    ingest(kb, embedder, store)
    (kb / "profile.md").write_text(PROFILE.replace("Backend engineer.", "Staff engineer."))
    embedder.embedded.clear()

    report = ingest(kb, embedder, store)

    assert report.updated == 1
    assert embedder.embedded == ["Ada > Summary\n\nStaff engineer."]


def test_deleting_a_file_removes_its_chunks(kb):
    store = InMemoryStore()
    ingest(kb, FakeEmbedder(), store)
    (kb / "experience" / "skills.md").unlink()

    report = ingest(kb, FakeEmbedder(), store)

    assert report.deleted == 1
    assert len(store.fingerprints()) == 2


def test_files_under_underscore_folders_are_drafts_and_skipped(kb):
    (kb / "_drafts").mkdir()
    (kb / "_drafts" / "secret.md").write_text("## Salary\n\nNot for publishing.\n")

    report = ingest(kb, FakeEmbedder(), InMemoryStore())

    assert report.added == 3


def test_a_different_embedding_model_fails_and_points_to_rebuild(kb):
    store = InMemoryStore()
    ingest(kb, FakeEmbedder(model="bge-m3", dimension=8), store)

    with pytest.raises(EmbeddingModelMismatch, match=r"make ingest REBUILD=1"):
        ingest(kb, FakeEmbedder(model="nomic-embed-text", dimension=8), store)


def test_rebuild_starts_over_with_the_new_model(kb):
    store = InMemoryStore()
    ingest(kb, FakeEmbedder(model="bge-m3", dimension=8), store)

    report = ingest(kb, FakeEmbedder(model="other", dimension=4), store, rebuild=True)

    assert report.added == 3
    assert store.get_model().name == "other"
