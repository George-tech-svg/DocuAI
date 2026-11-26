"""Extract readable text from PDF, Word, and plain text files."""

from io import BytesIO

def extract_pages(name: str, content: bytes):
    """Read text from the uploaded file and preserve page numbers where available."""
    if name.lower().endswith('.pdf'):
        # pypdf keeps the serverless bundle smaller than a native PDF engine,
        # while supporting text extraction from normal, non-scanned PDFs.
        from pypdf import PdfReader

        pdf = PdfReader(BytesIO(content), strict=False)
        return [(i + 1, page.extract_text() or '') for i, page in enumerate(pdf.pages)]
    if name.lower().endswith('.docx'):
        from docx import Document as WordDocument

        doc = WordDocument(BytesIO(content))
        text = '\n'.join((p.text for p in doc.paragraphs))
        return [(1, text)]
    return [(1, content.decode('utf-8-sig', errors='replace'))]
