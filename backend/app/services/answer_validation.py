"""Post-generation citation and key-number checks for grounded answers."""
from __future__ import annotations
import re
from dataclasses import dataclass

FALLBACK_ANSWER = 'I could not find a reliable answer in your documents.'
CITATION_RE = re.compile(r'\[(\d+)\]')
NUMBER_RE = re.compile(r'(?<![\w])(?:KES\s*)?\d+(?:[,.]\d+)*(?:\s?(?:%|percent|days?|weeks?|months?|years?|KSh|KES))?(?![\w])', re.I)
DATE_RE = re.compile(r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{2,4})\b', re.I)

@dataclass(frozen=True)
class AnswerCheck:
    valid: bool
    reasons: tuple[str, ...]

def _normalize_number(value: str) -> str:
    return re.sub(r'[^\d]', '', value)

def validate_grounded_answer(answer: str, passages: list[str]) -> AnswerCheck:
    refs = [int(ref) for ref in CITATION_RE.findall(answer)]
    if not answer.strip(): return AnswerCheck(False, ('empty answer',))
    if not passages: return AnswerCheck(False, ('no evidence passages',))
    if not refs: return AnswerCheck(False, ('answer has no source citations',))
    reasons: list[str] = []
    if any(ref < 1 or ref > len(passages) for ref in refs): reasons.append('citation number does not exist')
    # Check numerical/date details only against the passages cited in that sentence.
    for sentence in re.split(r'(?<=[.!?])\s+|\n+', answer):
        sentence = re.sub(r'^\s*(?:[-*]\s*)?\d+[.)]\s+', '', sentence)
        if not sentence.strip() or sentence.lstrip().startswith('#') or sentence.strip().startswith('*General information only'):
            continue
        sentence_refs = [int(ref) for ref in CITATION_RE.findall(sentence)]
        if not sentence_refs:
            reasons.append('factual sentence has no citation')
            continue
        valid_passages = [passages[ref - 1] for ref in sentence_refs if 1 <= ref <= len(passages)]
        if not valid_passages: continue
        evidence = ' '.join(valid_passages).lower()
        claim = CITATION_RE.sub('', sentence)
        for value in DATE_RE.findall(claim):
            if re.sub(r'\s+', '', value.lower()) not in re.sub(r'\s+', '', evidence):
                reasons.append(f'date not present in cited source: {value}')
        for value in NUMBER_RE.findall(claim):
            normalized = _normalize_number(value)
            # Avoid checking lone Markdown list numbers and tiny incidental values.
            if len(normalized) >= 2 and normalized not in _normalize_number(evidence):
                reasons.append(f'number not present in cited source: {value}')
    return AnswerCheck(not reasons, tuple(dict.fromkeys(reasons)))

def confidence_from_retrieval(top_fusion_score: float, agreeing_passages: int) -> tuple[float, str]:
    """A cautious display heuristic, not a calibrated probability of truth."""
    max_single_hit_score = 2 / 61
    normalized = min(1.0, max(0.0, top_fusion_score / max_single_hit_score))
    agreement_bonus = min(max(agreeing_passages, 0), 3) / 3 * 0.25
    score = round(min(1.0, normalized * 0.75 + agreement_bonus), 3)
    if score >= 0.75: return score, 'Strong match'
    if score >= 0.35: return score, 'Partial match'
    return score, 'Weak match'
