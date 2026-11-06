"""Extract readable text from PDF, Word, and plain text files."""

from io import BytesIO
import fitz
from docx import Document as WordDocument

def extract_pages(name: str, content: bytes):
    """Read text from the uploaded file and preserve page numbers where available."""
    if name.lower().endswith('.pdf'):
        with fitz.open(stream=content, filetype='pdf') as pdf:
            return [(i + 1, page.get_text('text')) for i, page in enumerate(pdf)]
    if name.lower().endswith('.docx'):
        doc = WordDocument(BytesIO(content))
        text = '\n'.join((p.text for p in doc.paragraphs))
        return [(1, text)]
    return [(1, content.decode('utf-8-sig', errors='replace'))]
