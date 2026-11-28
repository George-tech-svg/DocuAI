from app.services.answer_validation import confidence_from_retrieval, validate_grounded_answer
from app.services.language import detect_language, requested_language, requested_translation_language
import asyncio
import importlib
import sys
import types


def test_detects_kiswahili_and_mixed_sheng():
    assert detect_language('Tafadhali eleza maana ya malipo haya') == 'sw'
    assert detect_language('Niaje, explain hii issue tafadhali') == 'mixed'
    assert requested_language('Please explain the payment date', 'sw') == 'sw'


def test_explicit_translation_request():
    assert requested_translation_language('Please translate this into Kiswahili') == 'sw'
    assert requested_translation_language('Tafadhali tafsiri hii kwa English') == 'en'
    assert requested_translation_language('Summarize this file') is None


def test_grounded_citations_and_numeric_checks():
    source = 'Payment of KSh 150 is due by 5 March 2027.'
    assert validate_grounded_answer('Payment is KSh 150 [1].', [source]).valid
    assert not validate_grounded_answer('Payment is KSh 250 [1].', [source]).valid
    assert not validate_grounded_answer('Payment is KSh 150 [2].', [source]).valid
    assert not validate_grounded_answer('Payment is KSh 150.', [source]).valid


def test_match_confidence_is_cautious_and_monotonic():
    weak, weak_label = confidence_from_retrieval(0.0, 0)
    strong, strong_label = confidence_from_retrieval(2 / 61, 3)
    assert weak == 0 and weak_label == 'Weak match'
    assert strong > weak and strong_label == 'Strong match'


def test_trusted_answer_retries_once_then_uses_exact_fallback(monkeypatch):
    calls = []

    async def fake_answer(*args, **kwargs):
        calls.append(kwargs.get('strict_grounding', False))
        return 'The fee is KSh 999 [1].'

    # Import with a small mocked provider module so this service test remains
    # runnable even in a lightweight environment without FastAPI installed.
    provider = types.ModuleType('app.services.llm')
    provider.answer_question = fake_answer
    monkeypatch.setitem(sys.modules, 'app.services.llm', provider)
    trusted_answers = importlib.import_module('app.services.trusted_answers')
    monkeypatch.setattr(trusted_answers, 'answer_question', fake_answer)
    answer, valid = asyncio.run(trusted_answers.trusted_answer(
        'What is the fee?', 'The fee is KSh 150.', ['The fee is KSh 150.'], language='en'))
    assert calls == [False, True]
    assert valid is False
    assert answer == 'I could not find a reliable answer in your documents.'
