from pathlib import Path
import pytest

from app.services import ocr


def test_scanned_pdf_page_uses_ocr_fallback(monkeypatch):
    pytest.importorskip('fitz')
    fixture = Path(__file__).parent / 'fixtures' / 'scanned_sample.pdf'
    content = fixture.read_bytes()
    called = []
    monkeypatch.setattr(ocr, '_ocr_image', lambda image: ('Sample scanned page text', 87.5))

    result = ocr.extract_document('scanned_sample.pdf', content, on_ocr=lambda: called.append(True))

    assert result['ocr_used'] is True
    assert result['ocr_confidence'] == 87.5
    assert result['pages'] == [(1, 'Sample scanned page text'), (2, 'Sample scanned page text')]
    assert called == [True, True]


def test_bad_scanned_page_is_recorded_without_raising(monkeypatch):
    pytest.importorskip('fitz')
    fixture = Path(__file__).parent / 'fixtures' / 'scanned_sample.pdf'
    calls = iter([
        lambda image: (_ for _ in ()).throw(RuntimeError('tesseract failed')),
        lambda image: ('Second page text', 91.0),
    ])
    monkeypatch.setattr(ocr, '_ocr_image', lambda image: next(calls)(image))

    result = ocr.extract_document('scanned_sample.pdf', fixture.read_bytes())

    assert result['ocr_used'] is True
    assert result['ocr_failures'] == 1
    assert result['pages'] == [(1, ''), (2, 'Second page text')]
