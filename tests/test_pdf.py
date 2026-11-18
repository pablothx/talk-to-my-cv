from pathlib import Path

from talk_to_my_cv.chunking import chunk_document
from talk_to_my_cv.ingest import load_chunks
from talk_to_my_cv.pdf import markdown_from_cv_text

CV_TEXT = """Ana Gómez
Data Engineer | Spark
Córdoba, Argentina | ana@example.com
PROFESSIONAL SUMMARY
Data engineer who builds batch and streaming pipelines.
PROFESSIONAL EXPERIENCE
Senior Data Engineer, Acme Corp (2021 – Present)
Built the Spark pipelines that feed the billing reports.
Data Analyst, Initech (2018 - 2021)
Wrote the SQL behind the churn dashboard.
EDUCATION
Systems Engineer, UTN, Córdoba
"""


def test_the_first_line_is_the_title_and_the_header_lines_open_the_document():
    markdown = markdown_from_cv_text(CV_TEXT)

    assert markdown.startswith("---\ntitle: Ana Gómez\n---\n# Ana Gómez\n")
    assert "Data Engineer | Spark" in markdown.split("## ")[0]


def test_all_caps_lines_become_sections_and_dated_lines_become_subsections():
    markdown = markdown_from_cv_text(CV_TEXT)

    assert "\n## Professional summary\n" in markdown
    assert "\n## Professional experience\n" in markdown
    assert "\n### Senior Data Engineer, Acme Corp (2021 – Present)\n" in markdown
    assert "\n### Data Analyst, Initech (2018 - 2021)\n" in markdown
    assert "\n## Education\n" in markdown


def test_each_job_is_its_own_chunk_with_the_company_in_the_breadcrumb():
    chunks = chunk_document("cv.pdf", markdown_from_cv_text(CV_TEXT))

    [acme] = [c for c in chunks if "Acme Corp" in c.section]
    assert (
        acme.section == "Professional experience > Senior Data Engineer, Acme Corp (2021 – Present)"
    )
    assert "Spark pipelines" in acme.text
    assert "Initech" not in acme.text
    assert all(c.text.strip() for c in chunks)


def test_ingest_reads_pdfs_next_to_markdown(tmp_path: Path):
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-fake")
    (tmp_path / "notes.md").write_text("---\ntitle: Notes\n---\n## Extra\n\nLikes chess.\n")

    chunks = load_chunks(tmp_path, pdf_text=lambda path: CV_TEXT)

    files = {c.file for c in chunks}
    assert files == {"cv.pdf", "notes.md"}
