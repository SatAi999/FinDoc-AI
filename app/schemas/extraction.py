from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional

class EvidenceSchema(BaseModel):
    source_text: Optional[str] = None
    page_number: Optional[int] = 1
    bounding_box: Optional[List[float]] = None

class ExtractedField(BaseModel):
    value: Any = None
    evidence: Optional[EvidenceSchema] = None

class InvoiceLineItem(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    line_total: Optional[float] = None

class InvoiceExtractionSchema(BaseModel):
    document_title: Optional[str] = "INVOICE"
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    po_number: Optional[str] = None
    payment_terms: Optional[str] = None
    payment_method: Optional[str] = None
    vendor_name: Optional[str] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tax_id: Optional[str] = None
    receipt_number: Optional[str] = None
    cashier: Optional[str] = None
    currency: Optional[str] = None
    subtotal: Optional[float] = None
    tax_amount: Optional[float] = None
    discount: Optional[float] = None
    total_amount: Optional[float] = None
    cash_paid: Optional[float] = None
    change_amount: Optional[float] = None
    line_items: List[InvoiceLineItem] = Field(default_factory=list)
    evidence: Dict[str, Optional[EvidenceSchema]] = Field(default_factory=dict)

class PeriodLineItem(BaseModel):
    line_item_name: str
    schedule: Optional[str] = None
    amount: Optional[float] = None
    values: Dict[str, Optional[float]] = Field(default_factory=dict)

class AdditionalDisclosureSchema(BaseModel):
    label: str
    schedule: Optional[str] = None
    amount: Optional[float] = None
    values: Dict[str, Optional[float]] = Field(default_factory=dict)

class BalanceSheetPeriodSchema(BaseModel):
    period_name: str  # e.g., "March 31, 2026", "2026", "2025"
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    total_capital_and_liabilities: Optional[float] = None
    asset_line_items: List[PeriodLineItem] = Field(default_factory=list)
    liability_equity_line_items: List[PeriodLineItem] = Field(default_factory=list)

class BalanceSheetExtractionSchema(BaseModel):
    document_title: Optional[str] = None
    company_name: Optional[str] = None
    reporting_date: Optional[str] = None
    currency: Optional[str] = None
    unit: Optional[str] = None
    periods: List[BalanceSheetPeriodSchema] = Field(default_factory=list)
    additional_disclosures: List[AdditionalDisclosureSchema] = Field(default_factory=list)
    evidence: Dict[str, Optional[EvidenceSchema]] = Field(default_factory=dict)

class ProfitAndLossPeriodSchema(BaseModel):
    period_name: str  # e.g., "2026", "2025"
    revenue: Optional[float] = None
    cost_of_sales: Optional[float] = None
    gross_profit: Optional[float] = None
    interest_earned: Optional[float] = None
    other_income: Optional[float] = None
    total_income: Optional[float] = None
    operating_expenses: Optional[float] = None
    interest_expended: Optional[float] = None
    provisions_and_contingencies: Optional[float] = None
    total_expenditure: Optional[float] = None
    operating_profit: Optional[float] = None
    tax: Optional[float] = None
    net_profit_before_minority_interest: Optional[float] = None
    minority_interest: Optional[float] = None
    net_profit: Optional[float] = None
    current_profit: Optional[float] = None
    brought_forward_profit: Optional[float] = None
    total_available_for_appropriation: Optional[float] = None
    line_items: List[PeriodLineItem] = Field(default_factory=list)

class ProfitAndLossExtractionSchema(BaseModel):
    document_title: Optional[str] = None
    company_name: Optional[str] = None
    reporting_date: Optional[str] = None
    currency: Optional[str] = None
    unit: Optional[str] = None
    periods: List[ProfitAndLossPeriodSchema] = Field(default_factory=list)
    additional_disclosures: List[AdditionalDisclosureSchema] = Field(default_factory=list)
    evidence: Dict[str, Optional[EvidenceSchema]] = Field(default_factory=dict)

class CashFlowPeriodSchema(BaseModel):
    period_name: str
    operating_cash_flow: Optional[float] = None
    investing_cash_flow: Optional[float] = None
    financing_cash_flow: Optional[float] = None
    fx_translation_adjustment: Optional[float] = None
    net_change_in_cash: Optional[float] = None
    opening_cash: Optional[float] = None
    cash_acquired_adjustments: Optional[float] = None
    closing_cash: Optional[float] = None
    line_items: List[PeriodLineItem] = Field(default_factory=list)

class CashFlowExtractionSchema(BaseModel):
    document_title: Optional[str] = None
    company_name: Optional[str] = None
    reporting_date: Optional[str] = None
    currency: Optional[str] = None
    unit: Optional[str] = None
    periods: List[CashFlowPeriodSchema] = Field(default_factory=list)
    additional_disclosures: List[AdditionalDisclosureSchema] = Field(default_factory=list)
    evidence: Dict[str, Optional[EvidenceSchema]] = Field(default_factory=dict)
