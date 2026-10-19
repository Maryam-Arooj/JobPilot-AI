"""Read a CV file exactly like the app does and show timings + the quick result (no AI call, nothing saved).

Usage (repo root):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\test_my_cv.py "C:\\path\\to\\MARYAM AROOJ (CV).pdf"
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.services import document_service as ds  # noqa: E402
from backend.ai_agents.profile_agent import ProfileAgent  # noqa: E402

path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if not path or not path.exists():
    sys.exit('Give the CV path, e.g.  backend\\.venv\\Scripts\\python.exe backend\\scripts\\test_my_cv.py "C:\\Users\\vc\\Downloads\\MARYAM AROOJ (CV).pdf"')
data = path.read_bytes()
print(f"File: {path.name} ({len(data) // 1024} KB)")

if path.suffix.lower() == ".pdf":
    t0 = time.time(); a = ds._pdf_text_pymupdf(data); print(f"  PyMuPDF text layer : {len(a):5} chars  {time.time() - t0:.1f}s")
    t0 = time.time(); b = ds._pdf_text_pdfminer(data); print(f"  pdfminer text layer: {len(b):5} chars  {time.time() - t0:.1f}s")
    engine = ds._ocr_engine()
    hint = "NO  -> run: backend\\.venv\\Scripts\\pip install rapidocr onnxruntime"
    print("  local OCR installed: " + ("yes" if engine else hint))
    if engine and max(len(a), len(b)) < ds.MIN_TEXT_CHARS:
        t0 = time.time(); c = ds._ocr_pdf_local(data) or ""; print(f"  local OCR          : {len(c):5} chars  {time.time() - t0:.1f}s")

t0 = time.time()
text = ds.extract_text_from_file_bytes(data, path.name)
print(f"\nText used by the app: {len(text)} chars in {time.time() - t0:.1f}s")
print("-" * 80); print(text[:1500]); print("-" * 80)

t0 = time.time()
quick = ProfileAgent().quick_extract(text)
print(f"\nQuick read ({(time.time() - t0) * 1000:.0f} ms): {len(quick['facts'])} facts, missing: {quick['missing_fields']}")
print(json.dumps(quick["profile_data"], indent=1, ensure_ascii=False)[:3000])
