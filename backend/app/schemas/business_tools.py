"""Validated structured outputs and review requests for small-business tools."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class EvidenceClaim(BaseModel):
    value: str = Field(min_length=1, max_length=1200)
    source_id: str = Field(pattern=r'^(N|L)\d+$')
    quote: str = Field(min_length=3, max_length=900)
    confidence: float = Field(default=0.7, ge=0, le=1)


class NoticeDeadline(BaseModel):
    title: str = Field(min_length=2, max_length=220)
    due_at: datetime | None = None
    evidence: EvidenceClaim


class KRAOption(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    explanation: EvidenceClaim
    source_kind: Literal['library'] = 'library'


class KRAAnalysis(BaseModel):
    explanation: EvidenceClaim
    what_kra_requests: list[EvidenceClaim] = Field(default_factory=list, max_length=20)
    amounts: list[EvidenceClaim] = Field(default_factory=list, max_length=10)
    tax_type: EvidenceClaim | None = None
    deadlines: list[NoticeDeadline] = Field(default_factory=list, max_length=20)
    options: list[KRAOption] = Field(default_factory=list, max_length=10)
    documents_to_gather: list[EvidenceClaim] = Field(default_factory=list, max_length=30)
    draft_reply_letter: str = Field(min_length=1, max_length=12000)
    draft_citations: list[EvidenceClaim] = Field(default_factory=list, max_length=20)
    disclaimer: str = 'Information only, not tax or legal advice. Check the original notice and official sources before acting.'


class TenderRequirement(BaseModel):
    requirement: EvidenceClaim
    mandatory: bool = True
    category: str = Field(default='other', max_length=80)


class TenderAnalysis(BaseModel):
    tendering_entity: EvidenceClaim | None = None
    deadline: NoticeDeadline | None = None
    submission_method: EvidenceClaim | None = None
    eligibility_requirements: list[TenderRequirement] = Field(default_factory=list, max_length=80)
    mandatory_documents: list[TenderRequirement] = Field(default_factory=list, max_length=100)
    bid_security: EvidenceClaim | None = None
    evaluation_criteria: list[EvidenceClaim] = Field(default_factory=list, max_length=60)
    disclaimer: str = 'Information only. Check every requirement and deadline against the original tender document.'


class ReceiptLineItem(BaseModel):
    description: str = Field(min_length=1, max_length=240)
    quantity: Decimal | None = None
    amount: Decimal | None = None
    evidence: EvidenceClaim


class ReceiptAnalysis(BaseModel):
    supplier: EvidenceClaim | None = None
    supplier_pin: EvidenceClaim | None = None
    receipt_date: EvidenceClaim | None = None
    line_items: list[ReceiptLineItem] = Field(default_factory=list, max_length=100)
    vat_amount: EvidenceClaim | None = None
    total_amount: EvidenceClaim | None = None
    payment_method: EvidenceClaim | None = None
    disclaimer: str = 'Information only. These visible fields are not a verification of eTIMS validity.'


class AnalyzeDocumentRequest(BaseModel):
    document_id: UUID


class ConfirmToolRunRequest(BaseModel):
    output: dict | None = None
    have_items: list[str] = Field(default_factory=list, max_length=200)
    vault_matches: dict[str, UUID] = Field(default_factory=dict)


class VaultItemInput(BaseModel):
    document_id: UUID
    display_name: str = Field(min_length=1, max_length=220)
    category: str = Field(default='other', min_length=1, max_length=80)
    expires_at: datetime | None = None


class PayrollRateInput(BaseModel):
    code: str = Field(min_length=2, max_length=60, pattern=r'^[a-zA-Z0-9_-]+$')
    display_name: str = Field(min_length=2, max_length=160)
    rate_value: Decimal | None = Field(default=None, ge=0)
    rate_kind: Literal['percentage','fixed'] = 'percentage'
    tolerance_amount: Decimal = Field(default=Decimal('0'), ge=0)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    source_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=2000)

    def model_post_init(self, __context):
        if self.rate_value is not None and (self.effective_from is None or self.source_url is None):
            raise ValueError('A configured rate needs an effective start date and official source URL.')
        if self.effective_to and self.effective_from and self.effective_to < self.effective_from:
            raise ValueError('The end date must be on or after the start date.')


class PayrollCheckFinding(BaseModel):
    row_number: int = Field(ge=2)
    check: str = Field(min_length=2, max_length=180)
    actual: Decimal | None = None
    expected: Decimal | None = None
    message: str = Field(min_length=2, max_length=500)
    source_url: str | None = None


class PayrollCheckResult(BaseModel):
    rows_checked: int = Field(ge=0)
    configured_rates_used: list[str]
    findings: list[PayrollCheckFinding]
    information: str = 'Read-only arithmetic checks only. This is not a payroll, tax, or legal compliance determination.'
