from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip('fastapi')
pytest.importorskip('openpyxl')
pytest.importorskip('sqlalchemy')
pytest.importorskip('pgvector')

from fastapi import HTTPException

from app.api.v1.endpoints.business_tools import _payroll_rows, _receipt_totals_match, _validate_evidence
from app.schemas.business_tools import EvidenceClaim, ReceiptAnalysis, ReceiptLineItem

FIXTURES = Path(__file__).parent / 'fixtures' / 'business_tools'


def test_synthetic_kra_notice_is_plain_text_and_utf8_readable():
    text=(FIXTURES/'kra_notice_sample.txt').read_text(encoding='utf-8-sig')
    assert 'SYNTHETIC TEST FIXTURE' in text
    assert '15 March 2026' in text


def test_source_claim_must_quote_retrieved_passage():
    claim=EvidenceClaim(value='The notice shows KSh 12,500.',source_id='N1',
        quote='Amount shown: KSh 12,500.00.')
    sources={'N1':{'quote':'This training notice. Amount shown: KSh 12,500.00.'}}
    _validate_evidence(claim,sources)
    bad=EvidenceClaim(value='The amount is KSh 90,000.',source_id='N1',quote='KSh 90,000')
    with pytest.raises(ValueError,match='does not match'):
        _validate_evidence(bad,sources)


def test_kra_options_require_a_retrieved_library_citation():
    from app.schemas.business_tools import KRAAnalysis, KRAOption
    output=KRAAnalysis(explanation=EvidenceClaim(value='Notice summary.',source_id='N1',quote='Sample notice text.'),
        options=[KRAOption(title='Ask for clarification',explanation=EvidenceClaim(value='An option.',source_id='N1',quote='Sample notice text.'))],
        draft_reply_letter='Dear office, please clarify.',draft_citations=[])
    with pytest.raises(ValueError,match='official library'):
        _validate_evidence(output,{'N1':{'quote':'Sample notice text.'}},library_only_options=True)


def test_receipt_total_check_allows_visible_items_plus_vat():
    item=ReceiptLineItem(description='Paper',amount=Decimal('1000.00'),
        evidence=EvidenceClaim(value='KSh 1,000',source_id='N1',quote='Paper KSh 1,000.00'))
    receipt=ReceiptAnalysis(line_items=[item],vat_amount=EvidenceClaim(value='160',source_id='N1',quote='VAT KSh 160.00'),
        total_amount=EvidenceClaim(value='1160',source_id='N1',quote='TOTAL KSh 1,160.00'))
    assert _receipt_totals_match(receipt) is True


def test_payroll_fixture_loads_only_bounded_csv_data():
    headers,rows=_payroll_rows('payroll_sample.csv',(FIXTURES/'payroll_sample.csv').read_bytes())
    assert headers==['Employee ID','Gross Pay','Demo contribution','Net Pay']
    assert len(rows)==2


def test_payroll_rejects_file_without_gross_pay_column():
    with pytest.raises(HTTPException,match='gross'):
        _payroll_rows('payroll.csv',b'employee,net\n1,100\n')


def test_tender_fixture_contains_synthetic_deadline_only():
    text=(FIXTURES/'tender_sample.txt').read_text(encoding='utf-8-sig')
    assert 'SYNTHETIC TEST FIXTURE' in text
    assert '30 June 2026' in text


def test_receipt_fixture_disclaims_legal_or_etims_validity():
    text=(FIXTURES/'receipt_sample.txt').read_text(encoding='utf-8-sig')
    assert 'SYNTHETIC TEST FIXTURE' in text
    assert 'Supplier PIN' in text
