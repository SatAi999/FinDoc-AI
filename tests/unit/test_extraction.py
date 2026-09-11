import pytest
from app.services.ocr_service import OCRService
from app.services.extraction_service import ExtractionService

def test_ocr_extraction_native_pdf():
    with open("sample_documents/sample_invoice.pdf", "rb") as f:
        file_bytes = f.read()
    pages_data = OCRService.extract_text_and_layout(file_bytes, "sample_invoice.pdf")
    assert len(pages_data) == 1
    assert "ACME CORPORATION INVOICE" in pages_data[0]["full_text"]

def test_invoice_extraction():
    with open("sample_documents/sample_invoice.pdf", "rb") as f:
        file_bytes = f.read()
    pages_data = OCRService.extract_text_and_layout(file_bytes, "sample_invoice.pdf")
    extracted = ExtractionService.extract_structured_data(pages_data, "invoice")
    
    assert extracted["invoice_number"] == "INV-2023-001"
    assert extracted["subtotal"] == 3000.0
    assert extracted["total_amount"] == 3300.0
    assert len(extracted["line_items"]) == 2

def test_balance_sheet_multi_period_extraction():
    with open("sample_documents/sample_balance_sheet.pdf", "rb") as f:
        file_bytes = f.read()
    pages_data = OCRService.extract_text_and_layout(file_bytes, "sample_balance_sheet.pdf")
    extracted = ExtractionService.extract_structured_data(pages_data, "balance_sheet")
    
    assert "periods" in extracted
    assert len(extracted["periods"]) >= 2
    period_2023 = [p for p in extracted["periods"] if "2023" in str(p.get("period_name", ""))][0]
    assert period_2023["total_assets"] == 500000.0
    assert period_2023["total_liabilities"] == 200000.0
    assert period_2023["total_equity"] == 300000.0

def test_cash_flow_bracketed_negative_parsing():
    val = ExtractionService._parse_amount("(50,000.00)")
    assert val == -50000.0

def test_invoice_two_column_line_items_without_qty_price():
    lines = [
        "COFFEE SHOP RECEIPT",
        "Invoice # REC-9081",
        "Date: 2026-03-31",
        "Due Date: 2026-04-15",
        "P.O. # PO-7788",
        "Payment Method: VISA",
        "Tel: 555-0199",
        "Email: info@coffeeshop.com",
        "Tax ID: TAX-99112",
        "Cashier: Alice",
        "ESPOT SHOT 4.50 T",
        "BLUEBERRY MUFFIN 3.50",
        "Subtotal: $8.00",
        "Tax: $0.80",
        "Total Amount: $8.80"
    ]
    extracted = ExtractionService._parse_rule_invoice(lines, "\n".join(lines), [{"full_text": "\n".join(lines), "page_number": 1}])
    assert extracted["invoice_number"] == "REC-9081"
    assert extracted["due_date"] == "2026-04-15"
    assert extracted["po_number"] == "PO-7788"
    assert extracted["payment_method"] == "VISA"
    assert extracted["phone"] == "555-0199"
    assert extracted["email"] == "info@coffeeshop.com"
    assert extracted["tax_id"] == "TAX-99112"
    assert extracted["cashier"] == "Alice"
    assert len(extracted["line_items"]) >= 2
    item1 = extracted["line_items"][0]
    assert item1["quantity"] is None
    assert item1["unit_price"] is None
    assert item1["line_total"] == 4.50

def test_grounding_verification_resets_ungrounded_numeric_values():
    data = {
        "subtotal": 100.0,
        "total_amount": 9999.99,  # Ungrounded hallucinated amount not present in source text
        "line_items": [{"description": "Widget", "line_total": 100.0}]
    }
    source_text = "Subtotal 100.00 Widget 100.00 Total Amount 100.00"
    verified = ExtractionService._verify_grounding_pass(data, source_text)
    assert verified["subtotal"] == 100.0
    assert verified["total_amount"] is None  # Ungrounded number reset to None

