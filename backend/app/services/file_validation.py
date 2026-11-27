"""Reject unsupported, oversized, empty, or incorrectly identified files."""

from pathlib import Path
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
    return (name, ALLOWED[suffix])
