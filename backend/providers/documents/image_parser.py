from .base import DocumentParser

class ImageParser(DocumentParser):
    def parse(self, file_bytes: bytes, filename: str):
        # OCR placeholder
        return {"text": "OCR extracted text", "facts": []}
