from providers.documents.factory import get_parser

def test_parser_selection():
    p = get_parser("resume.pdf")
    assert p.__class__.__name__ == "PdfParser"
    p2 = get_parser("resume.docx")
    assert p2.__class__.__name__ == "DocxParser"
