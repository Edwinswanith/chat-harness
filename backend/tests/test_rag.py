from app.rag.chunker import chunk_text


def test_chunker_preserves_content_with_overlap():
    chunks = chunk_text("alpha " * 600, size=200, overlap=40)
    assert len(chunks) > 2
    assert chunks[0].startswith("alpha")
    assert chunks[-1].endswith("alpha")
