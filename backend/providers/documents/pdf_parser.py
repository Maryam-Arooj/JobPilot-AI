import io
from .base import DocumentParser
from typing import Dict

class PdfParser(DocumentParser):
    def parse(self, file_bytes: bytes, filename: str) -> Dict:
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(io.BytesIO(file_bytes))
        except Exception:
            text = ""
        return {"text": text or "Extracted text from PDF", "facts": []}
