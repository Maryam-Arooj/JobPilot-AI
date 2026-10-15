from .pdf_parser import PdfParser
from .docx_parser import DocxParser
from .text_parser import TextParser
from .image_parser import ImageParser

def get_parser(filename: str):
    ext = filename.lower().split(".")[-1]
    if ext == "pdf":
        return PdfParser()
    if ext in ["docx", "doc"]:
        return DocxParser()
    if ext == "txt":
        return TextParser()
    if ext in ["png", "jpg", "jpeg"]:
        return ImageParser()
    raise ValueError("Unsupported file type")
