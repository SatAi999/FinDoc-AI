from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
import datetime
from app.models.document import DocumentModel
from app.core.logging import logger

class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_or_update(
        self,
        document_name: str,
        document_type: str,
        processing_status: str,
        file_validation: Dict[str, Any],
        extracted_data: Optional[Dict[str, Any]],
        validation: Optional[Dict[str, Any]],
        processing_metadata: Dict[str, Any]
    ) -> DocumentModel:
        logger.info(f"Saving/updating document in DB: {document_name}")
        
        # Check if document already exists
        existing = self.db.query(DocumentModel).filter(DocumentModel.document_name == document_name).first()
        
        if existing:
            existing.document_type = document_type
            existing.processing_status = processing_status
            existing.file_validation = file_validation
            existing.extracted_data = extracted_data
            existing.validation = validation
            existing.processing_metadata = processing_metadata
            existing.updated_at = datetime.datetime.utcnow()
            doc_record = existing
            logger.info(f"Updated existing record for document: {document_name}")
        else:
            doc_record = DocumentModel(
                document_name=document_name,
                document_type=document_type,
                processing_status=processing_status,
                file_validation=file_validation,
                extracted_data=extracted_data,
                validation=validation,
                processing_metadata=processing_metadata
            )
            self.db.add(doc_record)
            logger.info(f"Created new database record for document: {document_name}")

        self.db.commit()
        self.db.refresh(doc_record)
        return doc_record

    def get_by_name(self, document_name: str) -> Optional[DocumentModel]:
        return self.db.query(DocumentModel).filter(DocumentModel.document_name == document_name).order_by(DocumentModel.updated_at.desc()).first()

    def list_all(self) -> List[DocumentModel]:
        return self.db.query(DocumentModel).order_by(DocumentModel.created_at.desc()).all()
