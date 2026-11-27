"""Per-page OCR helpers; native dependencies are installed on the worker only."""

from __future__ import annotations

from io import BytesIO
from statistics import mean
from zipfile import ZipFile, BadZipFile

OCR_LANGUAGE = 'eng+swa'
LOW_CONFIDENCE_THRESHOLD = 60.0
MIN_PAGE_TEXT_CHARS = 30


def _ocr_image(image) -> tuple[str, float | None]:
    import pytesseract
    from pytesseract import Output

    result = pytesseract.image_to_data(image, lang=OCR_LANGUAGE, output_type=Output.DICT)
    words: list[str] = []
    confidences: list[float] = []
    for word, raw_confidence in zip(result.get('text', []), result.get('conf', [])):
        word = word.strip()
        try:
            confidence = float(raw_confidence)
        except (TypeError, ValueError):
            continue
        if word and confidence >= 0:
            words.append(word)
            confidences.append(confidence)
    return ' '.join(words), mean(confidences) if confidences else None


def _open_image(content: bytes, suffix: str):
    from PIL import Image
    if suffix == '.heic':
        import pillow_heif
        pillow_heif.register_heif_opener()
    image = Image.open(BytesIO(content))
    if image.width <= 0 or image.height <= 0 or image.width * image.height > 16_000_000:
        raise ValueError('This image is too large to process safely. Please resize it and try again.')
    image = image.convert('RGB')
    if suffix == '.heic':
        converted = BytesIO()
        image.save(converted, format='JPEG', quality=92)
        converted.seek(0)
        image = Image.open(converted).convert('RGB')
    return image


def _ocr_pdf_page(pdf_page):
    import fitz
    from PIL import Image
    rect = pdf_page.rect
    if rect.width <= 0 or rect.height <= 0:
        raise ValueError('This PDF page has invalid dimensions.')
    scale = min(2.0, 6000 / max(rect.width, rect.height), (16_000_000 / (rect.width * rect.height)) ** 0.5)
    pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return Image.open(BytesIO(pixmap.tobytes('png'))).convert('RGB')


def extract_document(name: str, content: bytes, on_ocr=None) -> dict:
    """Extract text while OCRing only sparse PDF pages or image uploads.

    Individual OCR failures are recorded and skipped; another page can still
    produce a useful, ready document. The caller can surface a safe failure if
    no text was recovered from any page.
    """
    suffix = name.lower().rsplit('.', 1)[-1] if '.' in name else ''
    pages: list[tuple[int, str]] = []
    confidences: list[float] = []
    ocr_used = False
    ocr_failures = 0
    ocr_error = None

    def note_ocr_error(exc: Exception):
        nonlocal ocr_error
        message = str(exc)
        if isinstance(exc, ValueError) and (message.startswith('This image is too large') or message.startswith('This PDF page')):
            ocr_error = message
        elif ocr_error is None:
            ocr_error = 'We could not read text from a scanned page. Try a clearer scan or photo.'

    if suffix == 'txt':
        return {'pages': [(1, content.decode('utf-8-sig', errors='replace'))], 'ocr_used': False, 'ocr_confidence': None, 'ocr_failures': 0}
    if suffix == 'docx':
        from docx import Document as WordDocument
        try:
            with ZipFile(BytesIO(content)) as archive:
                members = archive.infolist()
                expanded_bytes = sum(member.file_size for member in members)
                if len(members) > 5000 or expanded_bytes > 50_000_000:
                    raise ValueError('This Word document expands beyond the safe processing limit.')
        except BadZipFile as exc:
            raise ValueError('This Word document is damaged or invalid.') from exc
        document = WordDocument(BytesIO(content))
        text = '\n'.join(p.text for p in document.paragraphs)
        for table in document.tables:
            text += '\n' + '\n'.join(' | '.join(cell.text for cell in row.cells) for row in table.rows)
        return {'pages': [(1, text)], 'ocr_used': False, 'ocr_confidence': None, 'ocr_failures': 0}

    if suffix in {'jpg', 'jpeg', 'png', 'heic'}:
        try:
            image = _open_image(content, f'.{suffix}')
            if on_ocr: on_ocr()
            text, confidence = _ocr_image(image)
            ocr_used = True
            confidences.append(confidence if confidence is not None else 0.0)
            pages.append((1, text))
        except Exception as exc:
            ocr_used = True
            ocr_failures += 1
            confidences.append(0.0)
            note_ocr_error(exc)
            pages.append((1, ''))
        return {'pages': pages, 'ocr_used': ocr_used, 'ocr_confidence': mean(confidences) if confidences else None, 'ocr_failures': ocr_failures, 'ocr_error': ocr_error}

    if suffix != 'pdf':
        raise ValueError('This file type is not supported. Upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file.')

    from pypdf import PdfReader
    from fitz import open as open_pdf
    reader = PdfReader(BytesIO(content), strict=False)
    rendered_pdf = None
    for index, page in enumerate(reader.pages):
        page_number = index + 1
        text = page.extract_text() or ''
        if len(text.strip()) < MIN_PAGE_TEXT_CHARS:
            ocr_used = True
            try:
                if on_ocr: on_ocr()
                if rendered_pdf is None:
                    rendered_pdf = open_pdf(stream=content, filetype='pdf')
                image = _ocr_pdf_page(rendered_pdf.load_page(index))
                ocr_text, confidence = _ocr_image(image)
                if ocr_text.strip():
                    text = ocr_text
                confidences.append(confidence if confidence is not None else 0.0)
            except Exception as exc:
                ocr_failures += 1
                confidences.append(0.0)
                note_ocr_error(exc)
        pages.append((page_number, text))
    if rendered_pdf is not None:
        rendered_pdf.close()
    return {'pages': pages, 'ocr_used': ocr_used, 'ocr_confidence': mean(confidences) if confidences else None, 'ocr_failures': ocr_failures, 'ocr_error': ocr_error}
