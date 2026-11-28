from pathlib import Path
import ast

import pytest

from app.schemas.chat import ChatRequest, Source
from app.services.library_ingestion import validate_official_source_url


def test_chat_accepts_library_and_combined_scopes():
    whole_library = ChatRequest(scope_type='library', question='What does this guide say?')
    combined = ChatRequest(scope_type='folder_library', scope_id='00000000-0000-0000-0000-000000000001', question='What are the rules?')
    assert whole_library.scope_id is None
    assert combined.scope_id is not None


def test_library_source_has_version_and_location_fields():
    source = Source(filename='Example Act — 2024 version', source_type='library', version_label='2024', section_title='section 4', page_number=2, excerpt='Example')
    assert source.document_id is None
    assert source.version_label == '2024'
    assert source.section_title == 'section 4'


def test_private_retriever_does_not_query_library_tables():
    path = Path(__file__).parents[1] / 'app' / 'services' / 'retrieval.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    identifiers = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert 'DocumentChunk' in identifiers
    assert 'LibraryChunk' not in identifiers
    assert 'LibraryDocument' not in identifiers


def test_direct_url_guard_requires_public_https_url():
    with pytest.raises(ValueError):
        validate_official_source_url('http://example.org/file.pdf')
    with pytest.raises(ValueError):
        validate_official_source_url('https://127.0.0.1/private.pdf')


def test_member_library_api_is_read_only_and_writes_are_admin_guarded():
    path = Path(__file__).parents[1] / 'app' / 'api' / 'v1' / 'endpoints' / 'library.py'
    source = path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    member_routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == 'router':
                        member_routes.append(decorator.func.attr.upper())
    assert member_routes and set(member_routes) == {'GET'}
    assert "admin_router = APIRouter(prefix='/admin/library'" in source
    assert 'dependencies=[Depends(admin_user)]' in source
