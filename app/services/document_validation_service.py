import os
import fitz  # PyMuPDF
from PIL import Image
from app.core.config import settings
from app.core.logging import logger
from app.schemas.document import FileValidationSchema

class DocumentValidationService:
    @staticmethod
    def validate_document(file_bytes: bytes, filename: str, content_type: str = "") -> FileValidationSchema:
        logger.info(f"Performing document validation for file: {filename}, size: {len(file_bytes)} bytes")
        
        # 1. File empty check
        if not file_bytes or len(file_bytes) == 0:
            logger.warning(f"Validation failed: Empty file {filename}")
            return FileValidationSchema(
                file_type=content_type or "unknown",
                is_supported=False,
                is_readable=False,
                page_count=0,
                status="FAILED",
                error_message="File is empty (0 bytes)."
            )
            
        # 2. File extension check
        ext = os.path.splitext(filename)[1].lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            logger.warning(f"Validation failed: Unsupported file extension '{ext}' for file {filename}")
            return FileValidationSchema(
                file_type=ext,
                is_supported=False,
                is_readable=False,
                page_count=0,
                status="FAILED",
                error_message=f"Unsupported file type '{ext}'. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

        # 3. Readability and Page Count Validation
        page_count = 0
        is_readable = False

        if ext == ".pdf":
            try:
                pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
                page_count = pdf_doc.page_count
                if page_count > 0:
                    is_readable = True
                pdf_doc.close()
            except Exception as e:
                logger.error(f"Corrupted or unreadable PDF: {filename}, error: {str(e)}")
                return FileValidationSchema(
                    file_type="pdf",
                    is_supported=True,
                    is_readable=False,
                    page_count=0,
                    status="FAILED",
                    error_message=f"Corrupted or unreadable PDF file: {str(e)}"
                )
        else: # Image files (.jpg, .jpeg, .png)
            try:
                import io
                image = Image.open(io.BytesIO(file_bytes))
                image.verify()
                page_count = 1
                is_readable = True
            except Exception as e:
                logger.error(f"Corrupted or unreadable Image: {filename}, error: {str(e)}")
                return FileValidationSchema(
                    file_type=ext.replace(".", ""),
                    is_supported=True,
                    is_readable=False,
                    page_count=0,
                    status="FAILED",
                    error_message=f"Corrupted or unreadable image file: {str(e)}"
                )

        # 4. Page count limit check (max 3 pages)
        if page_count > settings.MAX_PAGES:
            logger.warning(f"Validation failed: Page count {page_count} exceeds maximum allowed limit of {settings.MAX_PAGES}")
            return FileValidationSchema(
                file_type=ext.replace(".", ""),
                is_supported=True,
                is_readable=is_readable,
                page_count=page_count,
                status="FAILED",
                error_message=f"Page count ({page_count}) exceeds maximum allowed limit of {settings.MAX_PAGES} pages."
            )

        logger.info(f"Document validation PASSED for {filename}. Pages: {page_count}")
        return FileValidationSchema(
            file_type=ext.replace(".", ""),
            is_supported=True,
            is_readable=True,
            page_count=page_count,
            status="PASS"
        )
