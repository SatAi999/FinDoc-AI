import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Financial Document Intelligence Platform"
    API_V1_STR: str = "/api/v1"
    
    # Storage & DB
    DATABASE_URL: str = "sqlite:///./documents.db"
    
    # API Keys & Local LLMs
    GEMINI_API_KEY: Optional[str] = None
    GROK_API_KEY: Optional[str] = None
    GROQ_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OLLAMA_BASE_URL: Optional[str] = None
    OLLAMA_MODEL: str = "mistral:latest"
    
    # File Validation Limits
    MAX_PAGES: int = 3
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".jpg", ".jpeg", ".png"]
    ALLOWED_MIME_TYPES: List[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png"
    ]
    
    # Financial Validation Settings
    FINANCIAL_TOLERANCE: float = 0.05
    
    # Processing & OCR Configuration
    DISABLE_HEAVY_OCR: bool = False
    
    # Logging
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
