import pytest
from app.services.extraction_service import ExtractionService
from app.services.financial_validation_service import FinancialValidationService
from app.schemas.document import CheckStatusEnum

def test_invoice_direct_routing_and_extraction():
    lines = [
        "TAX INVOICE",
        "Invoice # 100234",
        "Date: 2026-03-31",
        "Vendor: Acme Corp",
        "Customer: Beta LLC",
        "Subtotal: $100.00",
        "Tax: $10.00",
        "Total Amount: $110.00"
    ]
    extracted = ExtractionService._parse_rule_invoice(lines, "\n".join(lines), [{"full_text": "\n".join(lines), "page_number": 1}])
    assert extracted["invoice_number"] == "100234"
    assert extracted["subtotal"] == 100.0
    assert extracted["total_amount"] == 110.0

def test_unknown_document_preserves_structure():
    lines = ["Generic unclassified document with no financial keywords"]
    extracted = ExtractionService._parse_rule_invoice(lines, "\n".join(lines), [{"full_text": "\n".join(lines), "page_number": 1}])
    assert extracted["document_title"] == "INVOICE"

def test_balance_sheet_does_not_use_invoice_validation():
    extracted = {
        "company_name": "Test Co",
        "periods": [
            {
                "period_name": "2026",
                "total_assets": 1000.0,
                "total_capital_and_liabilities": 1000.0
            }
        ]
    }
    val_res = FinancialValidationService.validate_financials(extracted, "balance_sheet")
    check_names = [c.name for c in val_res.checks]
    assert not any("Line Item" in name or "Tax & Subtotal" in name for name in check_names)
    assert any("Capital & Liabilities vs Assets" in name for name in check_names)

def test_balance_sheet_comparative_periods():
    lines = [
        "CONSOLIDATED BALANCE SHEET",
        "As at March 31, 2026",
        "March 31, 2026", "March 31, 2025",
        "CAPITAL AND LIABILITIES",
        "Total", "4,908,040.84", "4,392,417.42",
        "ASSETS",
        "Total", "4,908,040.84", "4,392,417.42"
    ]
    extracted = ExtractionService._parse_rule_balance_sheet(lines, "\n".join(lines), [{"full_text": "\n".join(lines), "page_number": 1}])
    periods = extracted.get("periods", [])
    period_names = [p["period_name"] for p in periods]
    assert "2026" in period_names
    assert "2025" in period_names

def test_balance_sheet_totals_reconcile():
    lines = [
        "CONSOLIDATED BALANCE SHEET",
        "As at March 31, 2026",
        "March 31, 2026", "March 31, 2025",
        "CAPITAL AND LIABILITIES",
        "Total", "4,908,040.84", "4,392,417.42",
        "ASSETS",
        "Total", "4,908,040.84", "4,392,417.42"
    ]
    extracted = ExtractionService._parse_rule_balance_sheet(lines, "\n".join(lines), [{"full_text": "\n".join(lines), "page_number": 1}])
    val_res = FinancialValidationService.validate_financials(extracted, "balance_sheet")
    
    check_2026 = next(c for c in val_res.checks if "[2026] Capital & Liabilities vs Assets" in c.name)
    check_2025 = next(c for c in val_res.checks if "[2025] Capital & Liabilities vs Assets" in c.name)
    
    assert check_2026.status == CheckStatusEnum.PASS
    assert check_2026.variance == 0.0
    assert check_2025.status == CheckStatusEnum.PASS
    assert check_2025.variance == 0.0
