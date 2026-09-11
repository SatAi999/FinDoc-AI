import os
import pytest
from app.database.database import SessionLocal, Base, engine
from app.services.document_service import DocumentService

Base.metadata.create_all(bind=engine)

DATASET_DIR = r"D:\Netstat_Assignment\New Dataset 1\New Dataset"

@pytest.mark.skipif(not os.path.exists(DATASET_DIR), reason="Company test dataset directory not found")
def test_company_dataset_balance_sheet():
    fpath = os.path.join(DATASET_DIR, "Balance Sheet", "Consolidated Balance Sheet 2017.pdf")
    if not os.path.exists(fpath):
        pytest.skip("Test file missing")
    with open(fpath, "rb") as f:
        file_bytes = f.read()

    db = SessionLocal()
    try:
        service = DocumentService(db)
        res = service.process_document(file_bytes, "Consolidated Balance Sheet 2017.pdf", "balance_sheet", "application/pdf")
        assert res.document_name == "Consolidated Balance Sheet 2017.pdf"
        assert res.file_validation.status == "PASS"
        assert res.processing_status == "PASS"
        assert res.extracted_data is not None
    finally:
        db.close()

@pytest.mark.skipif(not os.path.exists(DATASET_DIR), reason="Company test dataset directory not found")
def test_company_dataset_cash_flow():
    fpath = os.path.join(DATASET_DIR, "Cash Flows", "Consolidated Cash Flow Statement 2017.pdf")
    if not os.path.exists(fpath):
        pytest.skip("Test file missing")
    with open(fpath, "rb") as f:
        file_bytes = f.read()

    db = SessionLocal()
    try:
        service = DocumentService(db)
        res = service.process_document(file_bytes, "Consolidated Cash Flow Statement 2017.pdf", "cash_flow_statement", "application/pdf")
        assert res.document_name == "Consolidated Cash Flow Statement 2017.pdf"
        assert res.file_validation.status == "PASS"
        assert res.processing_status == "PASS"
        assert res.extracted_data is not None
    finally:
        db.close()

@pytest.mark.skipif(not os.path.exists(DATASET_DIR), reason="Company test dataset directory not found")
def test_company_dataset_invoice_jpg():
    fpath = os.path.join(DATASET_DIR, "Invoices", "X51005361895.jpg")
    if not os.path.exists(fpath):
        pytest.skip("Test file missing")
    with open(fpath, "rb") as f:
        file_bytes = f.read()

    db = SessionLocal()
    try:
        service = DocumentService(db)
        res = service.process_document(file_bytes, "X51005361895.jpg", "invoice", "image/jpeg")
        assert res.document_name == "X51005361895.jpg"
        assert res.file_validation.status == "PASS"
        assert res.processing_status == "PASS"
        assert res.extracted_data is not None
    finally:
        db.close()

@pytest.mark.skipif(not os.path.exists(DATASET_DIR), reason="Company test dataset directory not found")
def test_company_dataset_profit_and_loss():
    fpath = os.path.join(DATASET_DIR, "Profit & Loss", "Consolidated Profit & Loss 2017.pdf")
    if not os.path.exists(fpath):
        pytest.skip("Test file missing")
    with open(fpath, "rb") as f:
        file_bytes = f.read()

    db = SessionLocal()
    try:
        service = DocumentService(db)
        res = service.process_document(file_bytes, "Consolidated Profit & Loss 2017.pdf", "profit_and_loss", "application/pdf")
        assert res.document_name == "Consolidated Profit & Loss 2017.pdf"
        assert res.file_validation.status == "PASS"
        assert res.processing_status == "PASS"
        assert res.extracted_data is not None
    finally:
        db.close()
