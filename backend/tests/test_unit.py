from app.services.chunking import chunk_pages
from app.services.file_validation import validate_upload
from fastapi import HTTPException
from app.schemas.auth import UserRegister

def test_chunking():
    result = chunk_pages([(1, 'hello world ' * 200)], size=200, overlap=20)
    assert len(result) > 1 and all((page == 1 for page, _ in result))

def test_validate_txt():
    assert validate_upload('notes.txt', b'hello', 10) == ('notes.txt', 'text/plain')

def test_reject_invalid_pdf():
    try:
        validate_upload('bad.pdf', b'hello', 10)
    except HTTPException as e:
        assert e.status_code == 400
    else:
        assert False

def test_four_digit_password_is_valid():
    assert UserRegister(full_name='Example User', email='a@example.com', password='1234')

def test_password_shorter_than_four_is_rejected():
    from pydantic import ValidationError
    try:
        UserRegister(full_name='Example User', email='a@example.com', password='123')
    except ValidationError:
        return
    assert False
