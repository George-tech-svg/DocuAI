from fastapi.testclient import TestClient

from app.main import app


def test_vercel_chat_preflight_is_allowed():
    client = TestClient(app)
    response = client.options(
        '/api/v1/chat',
        headers={
            'Origin': 'https://docu-ai-sage.vercel.app',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'authorization,content-type',
        },
    )

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://docu-ai-sage.vercel.app'
    assert 'POST' in response.headers['access-control-allow-methods']


def test_health_has_cors_header_for_vercel():
    response = TestClient(app).get(
        '/api/v1/health', headers={'Origin': 'https://docu-ai-sage.vercel.app'}
    )

    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://docu-ai-sage.vercel.app'
