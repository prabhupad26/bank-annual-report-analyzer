from bank_analyzer.retrieval.chunking import chunk_page

def test_chunk_page_preserves_content():
    chunks = chunk_page("one two three four", "report.pdf", 2, max_chars=9)
    assert " ".join(c.text for c in chunks) == "one two three four"
    assert all(c.page == 2 for c in chunks)

def test_long_token():
    chunks = chunk_page("abcdefghij", "report.pdf", 1, max_chars=4)
    assert [c.text for c in chunks] == ["abcd", "efgh", "ij"]
