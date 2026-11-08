import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import llm


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {'choices': [{'message': {'content': 'The document says Power BI is used for reporting.'}}]}


class FakeAsyncClient:
    request = None

    def __init__(self, **kwargs):
        self.timeout = kwargs['timeout']

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, *, headers, json):
        FakeAsyncClient.request = {'url': url, 'headers': headers, 'json': json}
        return FakeResponse()


def test_answer_question_uses_supported_model_and_bearer_key(monkeypatch):
    monkeypatch.setattr(
        llm,
        'get_settings',
        lambda: SimpleNamespace(DEEPSEEK_API_KEY='test-only-key', DEEPSEEK_MODEL='deepseek-chat'),
    )
    monkeypatch.setattr(llm.httpx, 'AsyncClient', FakeAsyncClient)

    answer = asyncio.run(llm.answer_question('What is Power BI used for?', 'It is used for reporting.'))

    assert answer == 'The document says Power BI is used for reporting.'
    assert FakeAsyncClient.request['url'] == 'https://api.deepseek.com/chat/completions'
    assert FakeAsyncClient.request['headers']['Authorization'] == 'Bearer test-only-key'
    assert FakeAsyncClient.request['json']['model'] == 'deepseek-flash'
    assert FakeAsyncClient.request['json']['thinking'] == {'type': 'disabled'}
    assert FakeAsyncClient.request['json']['stream'] is False


def test_answer_question_fails_clearly_without_api_key(monkeypatch):
    monkeypatch.setattr(
        llm,
        'get_settings',
        lambda: SimpleNamespace(DEEPSEEK_API_KEY='', DEEPSEEK_MODEL='deepseek-flash'),
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(llm.answer_question('Question?', 'Source text.'))

    assert error.value.status_code == 503
    assert error.value.detail == 'DEEPSEEK_API_KEY is not configured'
