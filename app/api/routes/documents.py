import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.database.database import get_db
from app.core.logging import logger
from app.services.document_service import DocumentService
from app.schemas.document import (
    DocumentResponseSchema,
    DocumentListItemSchema,
    DocumentTypeEnum,
    ErrorResponseSchema
)

router = APIRouter(prefix="/api/v1", tags=["Documents"])

@router.get("/health", summary="Platform Health Check")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

@router.post(
    "/process",
    response_model=DocumentResponseSchema,
    summary="Process Financial Document (Alias)",
    include_in_schema=False
)
@router.post(
    "/documents/process",
    response_model=DocumentResponseSchema,
    summary="Process Financial Document",
    responses={
        400: {"model": ErrorResponseSchema, "description": "Invalid input or document type"},
        500: {"model": ErrorResponseSchema, "description": "Internal server error"}
    }
)
async def process_document(
    file: UploadFile = File(...),
    document_type: str = Form(...),
    db: Session = Depends(get_db)
):
    logger.info(f"Received upload request: file='{file.filename}', document_type='{document_type}'")
    
    # Normalize document type
    doc_type_clean = document_type.strip().lower()
    allowed_types = [t.value for t in DocumentTypeEnum]
    
    if doc_type_clean not in allowed_types:
        logger.warning(f"Invalid document type submitted: '{document_type}'")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "INVALID_DOCUMENT_TYPE",
                    "message": f"Unsupported document_type '{document_type}'. Must be one of: {', '.join(allowed_types)}"
                }
            }
        )

    try:
        file_bytes = await file.read()
        service = DocumentService(db)
        response = service.process_document(
            file_bytes=file_bytes,
            filename=file.filename,
            document_type=doc_type_clean,
            content_type=file.content_type or ""
        )
        return response
    except Exception as e:
        logger.error(f"Unexpected error while processing document '{file.filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "code": "INTERNAL_PROCESSING_ERROR",
                    "message": "An unexpected error occurred while processing the document."
                }
            }
        )

@router.get(
    "/documents/{document_name}",
    response_model=DocumentResponseSchema,
    summary="Get Latest Document Result by Name"
)
def get_document(document_name: str, db: Session = Depends(get_db)):
    import html, urllib.parse
    logger.info(f"GET document request for name: '{document_name}'")
    service = DocumentService(db)
    result = service.get_document_by_name(document_name)
    if not result:
        clean_name = html.unescape(urllib.parse.unquote(document_name))
        result = service.get_document_by_name(clean_name)
    if not result:
        logger.warning(f"Document not found: '{document_name}'")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "DOCUMENT_NOT_FOUND",
                    "message": f"No processed document found with name '{document_name}'"
                }
            }
        )
    return result

@router.get(
    "/documents",
    response_model=List[DocumentListItemSchema],
    summary="List Processed Documents"
)
def list_documents(db: Session = Depends(get_db)):
    logger.info("Listing all processed documents")
    service = DocumentService(db)
    return service.list_documents()
