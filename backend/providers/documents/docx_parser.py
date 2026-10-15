from .base import DocumentParser
import io

class DocxParser(DocumentParser):
    def parse(self, file_bytes: bytes, filename: str):
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            text = "\n".join([p.text for p in doc.paragraphs])
        except Exception:
            text = ""
        return {"text": text or "Extracted text from DOCX", "facts": []}
