import datetime
from sqlalchemy import Column, Integer, String, JSON, DateTime, Text
from app.database.database import Base

class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    document_name = Column(String(255), nullable=False, index=True)
    document_type = Column(String(50), nullable=False)
    processing_status = Column(String(20), nullable=False, default="FAILED")
    
    file_validation = Column(JSON, nullable=False)
    extracted_data = Column(JSON, nullable=True)
    validation = Column(JSON, nullable=True)
    processing_metadata = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
