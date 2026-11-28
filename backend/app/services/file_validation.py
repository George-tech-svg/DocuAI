"""Reject unsupported, oversized, empty, or incorrectly identified files."""

from pathlib import Path
from io import BytesIO
import warnings
import zipfile
from fastapi import HTTPException
ALLOWED = {
    '.pdf': 'application/pdf', '.txt': 'text/plain',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.heic': 'image/heic',
}

def _valid_signature(suffix: str, content: bytes) -> bool:
    if suffix == '.pdf': return content.startswith(b'%PDF-')
    if suffix in {'.jpg', '.jpeg'}: return content.startswith(b'\xff\xd8\xff')
    if suffix == '.png': return content.startswith(b'\x89PNG\r\n\x1a\n')
    if suffix == '.heic': return len(content) >= 12 and content[4:8] == b'ftyp' and content[8:12] in {b'heic', b'heix', b'hevc', b'hevx', b'mif1', b'msf1'}
    if suffix == '.docx': return content.startswith(b'PK\x03\x04')
    return True

def _check_docx_container(content: bytes, max_mb: int):
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if not entries or len(entries) > 2000:
                raise ValueError('The Word file contains too many archive entries.')
            total = 0
            for entry in entries:
                name = entry.filename.replace('\\', '/')
                if name.startswith('/') or any(part == '..' for part in name.split('/')):
                    raise ValueError('The Word file contains an unsafe archive path.')
                if entry.flag_bits & 0x1 or entry.file_size < 0:
                    raise ValueError('Encrypted or invalid Word archives are not supported.')
                total += entry.file_size
                if total > min(max_mb * 20_000_000, 200_000_000):
                    raise ValueError('The expanded Word file is too large.')
                if entry.file_size > 1_000_000 and entry.compress_size == 0:
                    raise ValueError('The Word file has a suspicious compressed entry.')
                if entry.compress_size and entry.file_size / entry.compress_size > 100:
                    raise ValueError('The Word file has an unsafe compression ratio.')
                if name.lower().endswith('vbaproject.bin'):
                    raise ValueError('Macro-enabled Word files are not supported.')
            names = {entry.filename for entry in entries}
            if '[Content_Types].xml' not in names or 'word/document.xml' not in names:
                raise ValueError('This is not a valid Word document.')
            if archive.testzip() is not None:
                raise ValueError('The Word document archive is damaged.')
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError('The Word document archive is damaged or invalid.') from exc

def _check_pdf_safety(content: bytes):
    try:
        from pypdf import PdfReader
        from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject
        reader = PdfReader(BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError('Password-protected PDFs are not supported.')
        if len(reader.pages) > 1000:
            raise ValueError('This PDF contains too many pages to process safely.')
        blocked = {'/JavaScript','/JS','/Launch','/EmbeddedFiles','/RichMedia','/XFA','/OpenAction','/AA'}
        stack = [reader.trailer]
        seen = set()
        checked = 0
        while stack:
            item = stack.pop()
            if isinstance(item, IndirectObject):
                key = (item.idnum, item.generation)
                if key in seen: continue
                seen.add(key)
                item = item.get_object()
            checked += 1
            if checked > 50_000:
                raise ValueError('This PDF has too many linked objects to process safely.')
            if isinstance(item, DictionaryObject):
                if any(str(key) in blocked for key in item.keys()):
                    raise ValueError('This PDF contains active content or embedded files that are not supported.')
                stack.extend(item.values())
            elif isinstance(item, ArrayObject):
                stack.extend(item)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('This PDF is damaged, invalid, or uses an unsupported feature.') from exc

def _check_text(content: bytes):
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try: text = content.decode('utf-16')
        except UnicodeDecodeError as exc: raise ValueError('TXT files must contain readable text.') from exc
    if any(ord(char) < 32 and char not in '\n\r\t\f' for char in text):
        raise ValueError('This TXT file contains unsupported binary data.')

def _check_image_dimensions(content: bytes, suffix: str):
    try:
        from PIL import Image, UnidentifiedImageError
        if suffix == '.heic':
            import pillow_heif
            pillow_heif.register_heif_opener()
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            image = Image.open(BytesIO(content))
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > 16_000_000:
                raise ValueError('This image is too large to process safely. Please resize it and try again.')
            image.verify()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError('This image is damaged or uses an unsupported format.') from exc

def validate_upload(filename: str, content: bytes, max_mb: int):
    """Check filename, extension, file size, and basic file signatures."""
    name = Path((filename or '').replace(chr(92), '/')).name
    suffix = Path(name).suffix.lower()
    if not name or len(name) > 255 or suffix not in ALLOWED:
        raise HTTPException(400, 'Invalid file type. Please upload a PDF, TXT, DOCX, JPG, PNG, or HEIC file.')
    if not content:
        raise HTTPException(400, 'File is empty')
    if len(content) > max_mb * 1_000_000:
        raise HTTPException(413, f'File is too large. Maximum size is {max_mb}MB.')
    if not _valid_signature(suffix, content):
        raise HTTPException(400, 'The file contents do not match the selected file type. Please choose a valid supported document or image.')
    try:
        if suffix == '.docx': _check_docx_container(content, max_mb)
        elif suffix == '.pdf': _check_pdf_safety(content)
        elif suffix == '.txt': _check_text(content)
        elif suffix in {'.jpg', '.jpeg', '.png', '.heic'}: _check_image_dimensions(content, suffix)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return (name, ALLOWED[suffix])
