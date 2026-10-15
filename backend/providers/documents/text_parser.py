from .base import DocumentParser

class TextParser(DocumentParser):
    def parse(self, file_bytes: bytes, filename: str):
        text = file_bytes.decode("utf-8", errors="ignore")
        return {"text": text, "facts": []}
