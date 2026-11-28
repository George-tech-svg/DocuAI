"""Lightweight English, Kiswahili and mixed/Sheng detection and query translation."""
from __future__ import annotations
import logging
import re
import httpx
from app.core.config import get_settings
from app.services.ai_provider import active_model_name, get_ai_provider

logger = logging.getLogger(__name__)
SW_MARKERS = {
    'habari','tafadhali','nini','kwa','hii','hiyo','hizi','hapo','vipi','gani','sana','ndio',
    'hapana','naomba','unaweza','maana','eleza','fafanua','muhtasari','mkataba','tarehe',
    'lini','kiasi','malipo','mkataba','nisaidie','nifafanulie','kwanini','kwa nini','imeandikwa',
    'yangu','yako','wetu','wapi','sheria','kifungu','nipe','onyesha','tafuta','kesho','jana',
}
SHENG_MARKERS = {'maze','niaje','sasa','rada','poa','mbogi','kudishi','manze','si poa','aje'}

def detect_language(text: str) -> str:
    """Heuristic language label: en, sw, or mixed. Not a language-identification model."""
    words = re.findall(r"[\w']+", (text or '').lower())
    joined = ' '.join(words)
    # Match whole words; substring checks cause false positives (for example,
    # a Sheng marker can accidentally occur inside an unrelated Swahili word).
    sw = sum(1 for marker in SW_MARKERS if marker in words or (' ' in marker and marker in joined))
    sheng = sum(1 for marker in SHENG_MARKERS if marker in words or (' ' in marker and marker in joined))
    english = sum(1 for token in words if token in {'the','is','are','what','when','where','how','why','please','explain','summarize','does','do','can','will','was','were','for','with','from','this','that','and','of','in','on'})
    if (sw and english) or sheng: return 'mixed'
    return 'sw' if sw else 'en'

def requested_language(text: str, preference: str = 'auto') -> str:
    if preference in {'en', 'sw'}: return preference
    detected = detect_language(text)
    return 'mixed' if detected == 'mixed' else detected

def requested_translation_language(text: str) -> str | None:
    value = (text or '').lower()
    if re.search(r'\b(translate|tafsiri|geuza)\b.{0,100}\b(kiswahili|swahili|sw)\b|\b(into|kwa)\s+(kiswahili|swahili)\b', value): return 'sw'
    if re.search(r'\b(translate|tafsiri|geuza)\b.{0,100}\b(english|kiingereza|en)\b|\b(into|kwa)\s+(english|kiingereza)\b', value): return 'en'
    return None

async def translate_search_query_to_english(question: str) -> str:
    """Translate only the retrieval query. Keep original user text for answering."""
    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY: return question
    try:
        model = active_model_name()
        result = await get_ai_provider().complete([
                    {'role': 'system', 'content': 'Translate the user question into a concise English search query. Preserve names, dates, amounts, and legal references. Do not answer or add facts. Return only the English query.'},
                    {'role': 'user', 'content': question}], model=model, temperature=0,
                max_tokens=120, timeout=httpx.Timeout(connect=5, read=10, write=5, pool=5))
        return result.strip() if result.strip() else question
    except Exception:
        logger.warning('Swahili search query translation failed; using the original wording.', exc_info=True)
        return question
