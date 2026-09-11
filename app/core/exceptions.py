class DocumentProcessingException(Exception):
    pass

class InvalidFileException(DocumentProcessingException):
    pass

class ExtractionException(DocumentProcessingException):
    pass
