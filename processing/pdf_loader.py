from __future__ import annotations

from pathlib import Path

try:
    import fitz
except ImportError as exc:
    raise ImportError(
        "PyMuPDF is required for PDF loading. Install dependencies with "
        "`pip install -r requirements.txt`."
    ) from exc


def load_pdf_pages(pdf_path: Path) -> list[dict]:
    pages: list[dict] = []

    with fitz.open(pdf_path) as document:
        for index, page in enumerate(document, start=1):
            text = page.get_text("text")
            pages.append({"page_number": index, "text": text})

    return pages
