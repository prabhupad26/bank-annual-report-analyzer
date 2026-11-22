import pytest

from bank_analyzer.ingestion.download import download_manifest
from bank_analyzer.retrieval.chunking import chunk_page


def test_chunk_page_preserves_content():
    chunks = chunk_page("one two three four", "report.pdf", 2, max_chars=9)
    assert " ".join(c.text for c in chunks) == "one two three four"
    assert all(c.page == 2 for c in chunks)

def test_long_token():
    chunks = chunk_page("abcdefghij", "report.pdf", 1, max_chars=4)
    assert [c.text for c in chunks] == ["abcd", "efgh", "ij"]


def test_download_manifest_ignores_comments_but_rejects_empty_manifest(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "bank,year,url\n# Replace with verified official links\n\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Manifest has no report entries"):
        download_manifest(manifest, tmp_path / "raw")


def test_download_manifest_reports_missing_required_values(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("bank,year,url\nhsbc,,https://example.com/report.pdf\n", encoding="utf-8")

    with pytest.raises(ValueError, match="row 2 is missing values for: year"):
        download_manifest(manifest, tmp_path / "raw")
