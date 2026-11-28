from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('pypdf')
pytest.importorskip('PIL')

from fastapi import HTTPException
from pypdf import PdfWriter
from pypdf.generic import NameObject, TextStringObject

from app.services.file_validation import validate_upload


def test_rejects_docx_with_path_traversal():
    data = BytesIO()
    with ZipFile(data, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', '<document/>')
        archive.writestr('../outside.txt', 'unsafe')
    with pytest.raises(HTTPException, match='unsafe archive path'):
        validate_upload('unsafe.docx', data.getvalue(), 10)


def test_rejects_docx_with_suspicious_expansion_ratio():
    data = BytesIO()
    with ZipFile(data, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', 'A' * 300_000)
    with pytest.raises(HTTPException, match='compression ratio'):
        validate_upload('bomb.docx', data.getvalue(), 10)


def test_rejects_pdf_with_open_action():
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.root_object.update({NameObject('/OpenAction'): TextStringObject('https://example.invalid')})
    data = BytesIO()
    writer.write(data)
    with pytest.raises(HTTPException, match='active content'):
        validate_upload('active.pdf', data.getvalue(), 10)
