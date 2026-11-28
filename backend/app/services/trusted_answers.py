"""Generate, verify and safely fall back for source-grounded answers."""
import re
from app.services.answer_validation import FALLBACK_ANSWER, validate_grounded_answer
from app.services.llm import answer_question

DOMAIN_TERMS = re.compile(r'\b(legal|law|act|statute|tax|taxation|medical|medicine|health|diagnos(?:is|e)|treatment|clinical|sheria|kodi|matibabu|afya|utambuzi)\b', re.I)

async def trusted_answer(question: str, context: str, passages: list[str], *, language: str,
                        library_mode: bool = False, strict_grounding: bool = False,
                        translation_target: str | None = None, whatsapp_mode: bool = False):
    if not passages:
        return FALLBACK_ANSWER, False
    answer = await answer_question(question, context, library_mode=library_mode,
        answer_language=language, strict_grounding=strict_grounding,
        translation_target=translation_target, whatsapp_mode=whatsapp_mode)
    check = validate_grounded_answer(answer, passages)
    if not check.valid:
        answer = await answer_question(question, context, library_mode=library_mode,
            answer_language=language, strict_grounding=True,
            translation_target=translation_target, whatsapp_mode=whatsapp_mode)
        check = validate_grounded_answer(answer, passages)
    if not check.valid:
        answer = FALLBACK_ANSWER
    if library_mode:
        answer += '\n\n*General information only, not legal or tax advice. Check the official source.*'
    elif DOMAIN_TERMS.search(question) or DOMAIN_TERMS.search(context):
        answer += '\n\n*General information only, not professional advice.*'
    return answer, check.valid
