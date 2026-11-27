"""Reject unsupported, oversized, empty, or incorrectly identified files."""

from pathlib import Path
from fastapi import HTTPException
ALLOWED = {'.pdf': 'application/pdf', '.txt': 'text/plain'}

def validate_upload(filename: str, content: bytes, max_mb: int):
    """Check filename, extension, file size, and basic file signatures."""
    name = Path((filename or '').replace(chr(92), '/')).name
    suffix = Path(name).suffix.lower()
    if not name or len(name) > 255 or suffix not in ALLOWED:
        raise HTTPException(400, 'Invalid file type. Please upload a PDF or TXT file.')
    if not content:
        raise HTTPException(400, 'File is empty')
    if len(content) > max_mb * 1_000_000:
        raise HTTPException(413, 'File is too large. Maximum size is 10MB.')
    if suffix == '.pdf' and (not content.startswith(b'%PDF-')):
        raise HTTPException(400, 'Invalid file type. Please upload a PDF or TXT file.')
    return (name, ALLOWED[suffix])
