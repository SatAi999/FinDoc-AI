import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_invalid_document_type_rejected():
    with open("sample_documents/sample_invoice.pdf", "rb") as f:
        response = client.post(
            "/api/v1/documents/process",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")},
            data={"document_type": "invalid_type"}
        )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_DOCUMENT_TYPE"

def test_process_invoice_pdf_success():
    with open("sample_documents/sample_invoice.pdf", "rb") as f:
        response = client.post(
            "/api/v1/documents/process",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")},
            data={"document_type": "invoice"}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "sample_invoice.pdf"
    assert data["document_type"] == "invoice"
    assert data["processing_status"] == "PASS"
    assert data["file_validation"]["status"] == "PASS"
    assert data["extracted_data"]["total_amount"] == 3300.0
    assert data["validation"]["overall_status"] == "PASS"

def test_get_document_by_name():
    # Process first
    with open("sample_documents/sample_invoice.pdf", "rb") as f:
        client.post(
            "/api/v1/documents/process",
            files={"file": ("sample_invoice.pdf", f, "application/pdf")},
            data={"document_type": "invoice"}
        )
    
    # GET by name
    response = client.get("/api/v1/documents/sample_invoice.pdf")
    assert response.status_code == 200
    data = response.json()
    assert data["document_name"] == "sample_invoice.pdf"

def test_get_document_not_found():
    response = client.get("/api/v1/documents/non_existent_doc.pdf")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "DOCUMENT_NOT_FOUND"

def test_list_documents():
    response = client.get("/api/v1/documents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
