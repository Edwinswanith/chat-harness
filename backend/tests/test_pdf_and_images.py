import base64
import asyncio

import pytest

from app.rag.ingestion_service import IngestionService
from app.services.file_service import ALLOWED_EXTENSIONS
from app.validation.artifact_validator import validate_output


def test_png_artifact_requires_real_png_signature():
    png = b"\x89PNG\r\n\x1a\nimage-data"
    name, data = validate_output({"name": "chart.png", "content_base64": base64.b64encode(png).decode()})
    assert name == "chart.png" and data == png
    with pytest.raises(ValueError, match="Invalid PNG"):
        validate_output({"name": "chart.png", "content_base64": base64.b64encode(b"not-an-image").decode()})


def test_pdf_extraction_accepts_a_valid_pdf():
    from pypdf import PdfWriter
    import io

    output = io.BytesIO()
    writer = PdfWriter(); writer.add_blank_page(width=72, height=72); writer.write(output)
    assert output.getvalue().startswith(b"%PDF-")
    ingestion = IngestionService(None, None, None, None)
    assert asyncio.run(ingestion._extract_text("source.pdf", output.getvalue())) == ""
    assert ".pdf" in ALLOWED_EXTENSIONS
