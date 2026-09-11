from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from enum import Enum

class DocumentTypeEnum(str, Enum):
    INVOICE = "invoice"
    BALANCE_SHEET = "balance_sheet"
    PROFIT_AND_LOSS = "profit_and_loss"
    CASH_FLOW_STATEMENT = "cash_flow_statement"

class ProcessingStatusEnum(str, Enum):
    PASS = "PASS"
    FAILED = "FAILED"

from app.schemas.validation import CheckStatusEnum, FinancialCheckResult, ValidationSummarySchema

class FileValidationSchema(BaseModel):
    file_type: str
    is_supported: bool
    is_readable: bool
    page_count: int
    status: str
    error_message: Optional[str] = None

class ProcessingMetadataSchema(BaseModel):
    ocr_used: bool
    processed_at: str
    processing_time_ms: float
    model_used: Optional[str] = "PyMuPDF/EasyOCR+Rules"

class DocumentResponseSchema(BaseModel):
    document_name: str
    document_type: str
    processing_status: str
    file_validation: FileValidationSchema
    extracted_data: Optional[Dict[str, Any]] = None
    validation: Optional[ValidationSummarySchema] = None
    processing_metadata: ProcessingMetadataSchema

class DocumentListItemSchema(BaseModel):
    id: int
    document_name: str
    document_type: str
    processing_status: str
    created_at: str
    page_count: int

class ErrorDetailSchema(BaseModel):
    code: str
    message: str

class ErrorResponseSchema(BaseModel):
    error: ErrorDetailSchema
