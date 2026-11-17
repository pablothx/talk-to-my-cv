from talk_to_my_cv.chunking import chunk_document

PROFILE = """---
type: profile
title: Ada Example
tags: [backend, cloud]
---
# Ada Example

Backend engineer based in Rosario.

## Summary

Ten years building payment systems.

## Languages

Spanish (native), English (C1).
"""


def test_each_h2_becomes_a_chunk_with_its_section_name():
    chunks = chunk_document("profile.md", PROFILE)

    sections = [c.section for c in chunks]
    assert "Summary" in sections
    assert "Languages" in sections
    summary = next(c for c in chunks if c.section == "Summary")
    assert summary.text == "Ten years building payment systems."
    assert summary.file == "profile.md"


def test_frontmatter_becomes_metadata_and_never_leaks_into_text():
    chunks = chunk_document("profile.md", PROFILE)

    assert all(
        c.metadata == {"type": "profile", "title": "Ada Example", "tags": ["backend", "cloud"]}
        for c in chunks
    )
    assert not any("tags:" in c.text for c in chunks)


def test_text_before_the_first_h2_is_kept_under_the_document_title():
    chunks = chunk_document("profile.md", PROFILE)

    intro = chunks[0]
    assert intro.section == "Ada Example"
    assert intro.text == "Backend engineer based in Rosario."


def test_breadcrumb_goes_only_into_the_embedded_text():
    summary = next(c for c in chunk_document("profile.md", PROFILE) if c.section == "Summary")

    assert summary.embed_text == "Ada Example > Summary\n\nTen years building payment systems."
    assert summary.text == "Ten years building payment systems."


EXPERIENCE = """---
type: experience
title: Northwind Payments
---
## Senior Backend Engineer

Owned the settlement service.

### Ledger rewrite

Rewrote the ledger in Java 21.

### On-call

Led the on-call rotation.

## Earlier role

Junior developer.
"""


def test_h3_splits_its_h2_and_section_path_joins_both_headings():
    chunks = chunk_document("experience/northwind.md", EXPERIENCE)

    assert [c.section for c in chunks] == [
        "Senior Backend Engineer",
        "Senior Backend Engineer > Ledger rewrite",
        "Senior Backend Engineer > On-call",
        "Earlier role",
    ]
    ledger = chunks[1]
    assert ledger.text == "Rewrote the ledger in Java 21."
    assert ledger.embed_text.startswith(
        "Northwind Payments > Senior Backend Engineer > Ledger rewrite\n"
    )


def _long_section(paragraphs: int) -> str:
    body = "\n\n".join(f"Paragraph {i}. " + "word " * 80 for i in range(paragraphs))
    return f"---\ntitle: Long\n---\n## Projects\n\n{body}\n"


def test_long_section_is_split_by_paragraph_under_the_size_limit():
    chunks = chunk_document("projects.md", _long_section(paragraphs=8))

    assert len(chunks) > 1
    assert all(len(c.text) <= 1500 for c in chunks)
    assert all(c.section == "Projects" for c in chunks)
    joined = "\n\n".join(c.text for c in chunks)
    assert all(f"Paragraph {i}." in joined for i in range(8))


def test_ids_are_stable_across_runs_and_unique_within_a_document():
    first = chunk_document("projects.md", _long_section(paragraphs=8))
    second = chunk_document("projects.md", _long_section(paragraphs=8))

    assert [c.id for c in first] == [c.id for c in second]
    assert len({c.id for c in first}) == len(first)


def test_content_hash_changes_only_for_the_edited_chunk():
    before = chunk_document("profile.md", PROFILE)
    after = chunk_document("profile.md", PROFILE.replace("Ten years", "Eleven years"))

    changed = [
        b.section for b, a in zip(before, after, strict=True) if b.content_hash != a.content_hash
    ]
    assert changed == ["Summary"]
    assert [b.id for b in before] == [a.id for a in after]


def test_metadata_is_json_safe_and_part_of_the_content_hash():
    dated = PROFILE.replace("tags: [backend, cloud]", "start: 2019-03-01")
    retagged = PROFILE.replace("tags: [backend, cloud]", "tags: [backend]")

    [dated_intro, *_] = chunk_document("profile.md", dated)
    [original, *_] = chunk_document("profile.md", PROFILE)
    [changed, *_] = chunk_document("profile.md", retagged)

    assert dated_intro.metadata["start"] == "2019-03-01"
    assert original.content_hash != changed.content_hash
