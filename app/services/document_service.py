import time
import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.logging import logger
from app.services.document_validation_service import DocumentValidationService
from app.services.ocr_service import OCRService
from app.services.extraction_service import ExtractionService
from app.services.financial_validation_service import FinancialValidationService
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentResponseSchema, FileValidationSchema, ProcessingMetadataSchema

class DocumentService:
    def __init__(self, db: Session):
        self.repository = DocumentRepository(db)

    def process_document(self, file_bytes: bytes, filename: str, document_type: str, content_type: str = "") -> DocumentResponseSchema:
        start_time = time.time()
        logger.info(f"Processing document pipeline started: '{filename}', submitted_type: '{document_type}'")

        # Step 1: File Boundary & Integrity Validation
        file_val: FileValidationSchema = DocumentValidationService.validate_document(file_bytes, filename, content_type)

        if file_val.status == "FAILED":
            logger.warning(f"Aborting document processing due to validation failure: {file_val.error_message}")
            processing_time_ms = round((time.time() - start_time) * 1000, 2)
            meta = ProcessingMetadataSchema(
                ocr_used=False,
                processed_at=datetime.datetime.utcnow().isoformat(),
                processing_time_ms=processing_time_ms,
                model_used="None (Validation Failed)"
            )
            
            # Persist failure record
            self.repository.save_or_update(
                document_name=filename,
                document_type=document_type,
                processing_status="FAILED",
                file_validation=file_val.model_dump(),
                extracted_data=None,
                validation=None,
                processing_metadata=meta.model_dump()
            )

            return DocumentResponseSchema(
                document_name=filename,
                document_type=document_type,
                processing_status="FAILED",
                file_validation=file_val,
                extracted_data=None,
                validation=None,
                processing_metadata=meta
            )

        # Step 2: OCR / Text Extraction
        ocr_used = False
        try:
            pages_data = OCRService.extract_text_and_layout(file_bytes, filename)
            ocr_used = any(p.get("is_scanned", False) for p in pages_data)
        except Exception as e:
            logger.error(f"OCR / Text Extraction Exception for {filename}: {e}", exc_info=True)
            processing_time_ms = round((time.time() - start_time) * 1000, 2)
            meta = ProcessingMetadataSchema(
                ocr_used=ocr_used,
                processed_at=datetime.datetime.utcnow().isoformat(),
                processing_time_ms=processing_time_ms,
                model_used="OCR Failed"
            )
            file_val.status = "FAILED"
            file_val.error_message = f"Text extraction error: {str(e)}"
            
            self.repository.save_or_update(
                document_name=filename,
                document_type=document_type,
                processing_status="FAILED",
                file_validation=file_val.model_dump(),
                extracted_data=None,
                validation=None,
                processing_metadata=meta.model_dump()
            )
            return DocumentResponseSchema(
                document_name=filename,
                document_type=document_type,
                processing_status="FAILED",
                file_validation=file_val,
                extracted_data=None,
                validation=None,
                processing_metadata=meta
            )

        # Step 3: Forensic & Intelligent Document Type Routing
        effective_document_type = document_type.strip().lower()
        
        # Forensic classifier: check filename and document content indicators
        fn_upper = filename.upper()
        detected_type = None
        if "PROFIT" in fn_upper or "P&L" in fn_upper or "LOSS" in fn_upper:
            detected_type = "profit_and_loss"
        elif "BALANCE" in fn_upper or "BALANCESHEET" in fn_upper or "BS" in fn_upper:
            detected_type = "balance_sheet"
        elif "CASH" in fn_upper or "FLOW" in fn_upper or "CASHFLOW" in fn_upper:
            detected_type = "cash_flow_statement"
        elif "INVOICE" in fn_upper or "RECEIPT" in fn_upper or "BILL" in fn_upper:
            detected_type = "invoice"

        if not detected_type and pages_data:
            sample_text = " ".join([p.get("full_text", "") for p in pages_data[:1]]).upper()
            if "PROFIT AND LOSS" in sample_text or "PROFIT & LOSS" in sample_text or "STATEMENT OF PROFIT" in sample_text:
                detected_type = "profit_and_loss"
            elif "BALANCE SHEET" in sample_text:
                detected_type = "balance_sheet"
            elif "CASH FLOW" in sample_text or "STATEMENT OF CASH FLOWS" in sample_text:
                detected_type = "cash_flow_statement"
            elif "TAX INVOICE" in sample_text or "INVOICE" in sample_text:
                detected_type = "invoice"

        if detected_type and detected_type != effective_document_type and effective_document_type == "invoice":
            logger.info(f"Forensic classifier auto-corrected document '{filename}' from '{effective_document_type}' to '{detected_type}'")
            effective_document_type = detected_type
        else:
            logger.info(f"Routing document '{filename}' as target type: '{effective_document_type}'")

        # Step 4: AI Structured Data Extraction
        try:
            extracted_data = ExtractionService.extract_structured_data(pages_data, effective_document_type)
            model_used = extracted_data.pop("_metadata", {}).get("model_used", "Rule-based Engine")
        except Exception as e:
            logger.error(f"AI Extraction Exception for {filename}: {e}", exc_info=True)
            processing_time_ms = round((time.time() - start_time) * 1000, 2)
            meta = ProcessingMetadataSchema(
                ocr_used=ocr_used,
                processed_at=datetime.datetime.utcnow().isoformat(),
                processing_time_ms=processing_time_ms,
                model_used="Extraction Failed"
            )
            return DocumentResponseSchema(
                document_name=filename,
                document_type=effective_document_type,
                processing_status="FAILED",
                file_validation=file_val,
                extracted_data=None,
                validation=None,
                processing_metadata=meta
            )

        # Step 5: Financial Formula Validation (Matching Classified Document Type)
        validation_summary = FinancialValidationService.validate_financials(extracted_data, effective_document_type)

        # Step 6: Separate Pipeline Processing Status
        processing_status = "PASS"

        processing_time_ms = round((time.time() - start_time) * 1000, 2)
        meta = ProcessingMetadataSchema(
            ocr_used=ocr_used,
            processed_at=datetime.datetime.utcnow().isoformat(),
            processing_time_ms=processing_time_ms,
            model_used=model_used
        )

        # Step 7: Database Persistence
        self.repository.save_or_update(
            document_name=filename,
            document_type=effective_document_type,
            processing_status=processing_status,
            file_validation=file_val.model_dump(),
            extracted_data=extracted_data,
            validation=validation_summary.model_dump(),
            processing_metadata=meta.model_dump()
        )

        logger.info(f"Successfully finished processing document: {filename} as '{effective_document_type}' in {processing_time_ms} ms.")

        return DocumentResponseSchema(
            document_name=filename,
            document_type=effective_document_type,
            processing_status=processing_status,
            file_validation=file_val,
            extracted_data=extracted_data,
            validation=validation_summary,
            processing_metadata=meta
        )

    def get_document_by_name(self, filename: str) -> Optional[DocumentResponseSchema]:
        import os
        record = self.repository.get_by_name(filename)
        if not record:
            return None

        # 1. Dynamic type self-healing if historical record had misclassified type
        fn_upper = record.document_name.upper()
        inferred_type = None
        if "PROFIT" in fn_upper or "P&L" in fn_upper or "LOSS" in fn_upper:
            inferred_type = "profit_and_loss"
        elif "BALANCE" in fn_upper or "BALANCESHEET" in fn_upper or "BS" in fn_upper:
            inferred_type = "balance_sheet"
        elif "CASH" in fn_upper or "FLOW" in fn_upper or "CASHFLOW" in fn_upper:
            inferred_type = "cash_flow_statement"

        doc_type = record.document_type
        if inferred_type and inferred_type != doc_type and doc_type == "invoice":
            doc_type = inferred_type
            record.document_type = inferred_type
            
            # If extracted_data was from invoice schema without periods, re-extract from dataset file if available
            if not record.extracted_data or not record.extracted_data.get("periods"):
                potential_dirs = [
                    os.path.join("New Dataset 1", "New Dataset", "Balance Sheet"),
                    os.path.join("New Dataset 1", "New Dataset", "Profit & Loss"),
                    os.path.join("New Dataset 1", "New Dataset", "Cash Flows"),
                    os.path.join("New Dataset 1", "New Dataset", "Invoices"),
                    "sample_documents"
                ]
                for pdir in potential_dirs:
                    fpath = os.path.join(pdir, record.document_name)
                    if os.path.exists(fpath):
                        try:
                            with open(fpath, "rb") as f:
                                file_bytes = f.read()
                            pages_data = OCRService.extract_text_and_layout(file_bytes, record.document_name)
                            extracted = ExtractionService.extract_structured_data(pages_data, doc_type)
                            extracted.pop("_metadata", None)
                            record.extracted_data = extracted
                            break
                        except Exception as e:
                            logger.warning(f"On-the-fly re-extraction failed for {record.document_name}: {e}")

        # 2. Dynamically re-evaluate financial formulas based on the current state of extracted_data
        validation_data = record.validation
        if record.extracted_data:
            val_summary = FinancialValidationService.validate_financials(record.extracted_data, doc_type)
            validation_data = val_summary.model_dump()
            record.validation = validation_data
        
        try:
            self.repository.db.commit()
        except Exception:
            self.repository.db.rollback()

        return DocumentResponseSchema(
            document_name=record.document_name,
            document_type=doc_type,
            processing_status=record.processing_status,
            file_validation=record.file_validation,
            extracted_data=record.extracted_data,
            validation=validation_data,
            processing_metadata=record.processing_metadata
        )

    def list_documents(self):
        records = self.repository.list_all()
        result = []
        needs_commit = False
        for r in records:
            doc_type = r.document_type
            fn_upper = r.document_name.upper()
            inferred = None
            if "PROFIT" in fn_upper or "P&L" in fn_upper or "LOSS" in fn_upper:
                inferred = "profit_and_loss"
            elif "BALANCE" in fn_upper or "BALANCESHEET" in fn_upper or "BS" in fn_upper:
                inferred = "balance_sheet"
            elif "CASH" in fn_upper or "FLOW" in fn_upper or "CASHFLOW" in fn_upper:
                inferred = "cash_flow_statement"
            if inferred and inferred != doc_type and doc_type == "invoice":
                doc_type = inferred
                r.document_type = inferred
                needs_commit = True

            result.append({
                "id": r.id,
                "document_name": r.document_name,
                "document_type": doc_type,
                "processing_status": r.processing_status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "page_count": r.file_validation.get("page_count", 1) if r.file_validation else 1
            })
        if needs_commit:
            try:
                self.repository.db.commit()
            except Exception:
                self.repository.db.rollback()
        return result
