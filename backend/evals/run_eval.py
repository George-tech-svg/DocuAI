"""Run the source-grounding evaluation against the configured answer model.

From backend: python -m evals.run_eval
Requires the same DEEPSEEK_API_KEY used by the API. This is an integration eval,
not an offline unit test; the included corpus is synthetic and intentionally small.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

from app.core.config import get_settings
from app.services.answer_validation import FALLBACK_ANSWER
from app.services.trusted_answers import trusted_answer

DATA = json.loads((Path(__file__).parent / 'dataset.json').read_text(encoding='utf-8'))
CITATION = re.compile(r'\[(\d+)\]')


async def run_case(case: dict, by_id: dict) -> dict:
    expected_ids = case['expected_source_passages']
    passages = [by_id[item] for item in expected_ids] if expected_ids else [p['text'] for p in DATA['passages']]
    context = '\n\n'.join(f'[{i}] Sample source, page {i}: {text}' for i, text in enumerate(passages, 1))
    started = time.perf_counter()
    answer, validated = await trusted_answer(case['question'], context, passages,
        language=case['language'], strict_grounding=not case['answerable'])
    latency_ms = (time.perf_counter() - started) * 1000
    citations = {int(n) for n in CITATION.findall(answer)}
    cited_ids = {expected_ids[n - 1] for n in citations if 1 <= n <= len(expected_ids)}
    citation_ok = (bool(citations) and cited_ids == set(expected_ids)) if case['answerable'] else not citations
    refusal_ok = (answer.strip() != FALLBACK_ANSWER) if case['answerable'] else answer.strip() == FALLBACK_ANSWER
    return {'id': case['id'], 'lang': case['language'], 'citation_ok': citation_ok,
            'refusal_ok': refusal_ok, 'ms': latency_ms, 'answer': answer, 'validated': validated}


async def main() -> int:
    if not get_settings().DEEPSEEK_API_KEY:
        print('DEEPSEEK_API_KEY is required to run this model evaluation.', file=sys.stderr)
        return 2
    by_id = {p['id']: p['text'] for p in DATA['passages']}
    cases = DATA['cases']
    if len(cases) < 40 or len({c['id'] for c in cases}) != len(cases):
        print('Evaluation dataset must contain at least 40 unique cases.', file=sys.stderr)
        return 2
    results = []
    for case in cases:
        try:
            result = await run_case(case, by_id)
        except Exception as exc:
            result = {'id': case['id'], 'lang': case['language'], 'citation_ok': False,
                      'refusal_ok': False, 'ms': 0.0, 'answer': f'ERROR: {type(exc).__name__}: {exc}', 'validated': False}
        results.append(result)
        print(f"{result['id']:5} {result['lang']:5} cite={'PASS' if result['citation_ok'] else 'FAIL':4} "
              f"refuse={'PASS' if result['refusal_ok'] else 'FAIL':4} {result['ms']:8.0f} ms | {result['answer'][:100].replace(chr(10), ' ')}")
    citation_accuracy = sum(r['citation_ok'] for r in results) / len(results)
    refusal_cases = [r for r, c in zip(results, cases) if not c['answerable']]
    refusal_accuracy = sum(r['refusal_ok'] for r in refusal_cases) / max(1, len(refusal_cases))
    latencies = sorted(r['ms'] for r in results)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * .95))]
    print('\nMetric                 Result       Threshold')
    print(f'Citation accuracy      {citation_accuracy:6.1%}       >= {float(os.getenv("EVAL_MIN_CITATION", ".90")):.0%}')
    print(f'Refusal accuracy       {refusal_accuracy:6.1%}       >= {float(os.getenv("EVAL_MIN_REFUSAL", ".90")):.0%}')
    print(f'Latency p95            {p95:6.0f} ms    <= {int(os.getenv("EVAL_MAX_P95_MS", "45000"))} ms')
    print(f'Mean latency           {statistics.mean(r["ms"] for r in results):6.0f} ms')
    if (citation_accuracy < float(os.getenv('EVAL_MIN_CITATION', '.90'))
            or refusal_accuracy < float(os.getenv('EVAL_MIN_REFUSAL', '.90'))
            or p95 > int(os.getenv('EVAL_MAX_P95_MS', '45000'))):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
