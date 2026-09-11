import pytest
from app.services.document_validation_service import DocumentValidationService
from app.services.financial_validation_service import FinancialValidationService
from app.schemas.document import CheckStatusEnum

def test_unsupported_file_extension():
    res = DocumentValidationService.validate_document(b"hello world", "test.txt", "text/plain")
    assert res.status == "FAILED"
    assert res.is_supported is False
    assert "Unsupported file type" in res.error_message

def test_empty_file():
    res = DocumentValidationService.validate_document(b"", "empty.pdf", "application/pdf")
    assert res.status == "FAILED"
    assert res.is_readable is False
    assert "empty" in res.error_message.lower()

def test_exceed_page_count_limit():
    import os
    with open("sample_documents/sample_invalid_pagecount.pdf", "rb") as f:
        file_bytes = f.read()
    res = DocumentValidationService.validate_document(file_bytes, "sample_invalid_pagecount.pdf", "application/pdf")
    assert res.status == "FAILED"
    assert res.page_count == 4
    assert "exceeds maximum allowed limit" in res.error_message

def test_valid_pdf_file():
    with open("sample_documents/sample_invoice.pdf", "rb") as f:
        file_bytes = f.read()
    res = DocumentValidationService.validate_document(file_bytes, "sample_invoice.pdf", "application/pdf")
    assert res.status == "PASS"
    assert res.page_count == 1
    assert res.is_supported is True

def test_invoice_financial_validation_pass():
    ext_data = {
        "subtotal": 3000.0,
        "tax_amount": 300.0,
        "discount": 0.0,
        "total_amount": 3300.0,
        "cash_paid": 3500.0,
        "change_amount": 200.0,
        "line_items": [
            {"quantity": 10.0, "unit_price": 150.0, "line_total": 1500.0},
            {"quantity": 2.0, "unit_price": 750.0, "line_total": 1500.0}
        ]
    }
    val = FinancialValidationService.validate_financials(ext_data, "invoice")
    assert val.overall_status == CheckStatusEnum.PASS
    assert all(c.status == CheckStatusEnum.PASS for c in val.checks)

def test_invoice_financial_validation_fail():
    ext_data = {
        "subtotal": 1000.0,
        "tax_amount": 100.0,
        "discount": 0.0,
        "total_amount": 1500.0 # Error: 1000 + 100 != 1500
    }
    val = FinancialValidationService.validate_financials(ext_data, "invoice")
    assert val.overall_status == CheckStatusEnum.FAIL
    assert any(c.status == CheckStatusEnum.FAIL for c in val.checks)

def test_missing_operands_not_applicable():
    ext_data = {
        "subtotal": 1000.0,
        "tax_amount": None,
        "total_amount": None
    }
    val = FinancialValidationService.validate_financials(ext_data, "invoice")
    assert any(c.status == CheckStatusEnum.NOT_APPLICABLE for c in val.checks)

def test_cash_flow_bracketed_negatives_validation():
    ext_data = {
        "periods": [
            {
                "period_name": "2023",
                "operating_cash_flow": 150000.0,
                "investing_cash_flow": -50000.0,
                "financing_cash_flow": -20000.0,
                "fx_translation_adjustment": 0.0,
                "net_change_in_cash": 80000.0,
                "opening_cash": 100000.0,
                "cash_acquired_adjustments": 0.0,
                "closing_cash": 180000.0
            }
        ]
    }
    val = FinancialValidationService.validate_financials(ext_data, "cash_flow_statement")
    assert val.overall_status == CheckStatusEnum.PASS

def test_balance_sheet_exact_and_rounding():
    # Exact balance check
    ext_pass = {
        "periods": [
            {
                "period_name": "2026",
                "total_assets": 1000000.0,
                "total_capital_and_liabilities": 1000000.0,
                "total_liabilities": 600000.0,
                "total_equity": 400000.0,
                "asset_line_items": [
                    {"line_item_name": "Cash", "amount": 500000.0},
                    {"line_item_name": "Investments", "amount": 500000.0}
                ]
            }
        ]
    }
    val_pass = FinancialValidationService.validate_financials(ext_pass, "balance_sheet")
    assert val_pass.overall_status == CheckStatusEnum.PASS
    assert all(c.status == CheckStatusEnum.PASS for c in val_pass.checks)

    # Imbalance check
    ext_fail = {
        "periods": [
            {
                "period_name": "2026",
                "total_assets": 1000000.0,
                "total_capital_and_liabilities": 1200000.0  # Imbalance
            }
        ]
    }
    val_fail = FinancialValidationService.validate_financials(ext_fail, "balance_sheet")
    assert val_fail.overall_status == CheckStatusEnum.FAIL

def test_profit_and_loss_negative_and_missing():
    # Exact P&L with negative expense/loss
    ext_pnl = {
        "periods": [
            {
                "period_name": "2026",
                "interest_earned": 50000.0,
                "other_income": 10000.0,
                "total_income": 60000.0,
                "operating_expenses": 70000.0,
                "total_expenditure": 70000.0,
                "net_profit": -10000.0  # Loss case
            }
        ]
    }
    val = FinancialValidationService.validate_financials(ext_pnl, "profit_and_loss")
    assert val.overall_status == CheckStatusEnum.PASS

def test_invoice_decimal_qty_and_discount():
    ext_inv = {
        "subtotal": 125.50,
        "discount": 10.0,
        "tax_amount": 11.55,
        "total_amount": 127.05,
        "cash_paid": 150.00,
        "change_amount": 22.95,
        "line_items": [
            {"quantity": 2.5, "unit_price": 50.20, "line_total": 125.50}
        ]
    }
    val = FinancialValidationService.validate_financials(ext_inv, "invoice")
    assert val.overall_status == CheckStatusEnum.PASS

