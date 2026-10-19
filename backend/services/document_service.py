import io
import logging
from typing import Any, Dict, List, Optional
import docx
from pdfminer.high_level import extract_text as extract_pdf_text
from ..ai_agents.profile_agent import ProfileAgent
from .agent_runs import run_warn, tool_call

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 150  # below this, a "PDF" is treated as image-only (design tool / scan)
MAX_OCR_PAGES = 3


def _pdf_text_pdfminer(file_bytes: bytes) -> str:
    try:
        return (extract_pdf_text(io.BytesIO(file_bytes)) or "").strip()
    except Exception as e:
        logger.warning("pdfminer could not read the PDF: %s", type(e).__name__)
        return ""


def _pdf_text_pymupdf(file_bytes: bytes) -> str:
    try:
        import pymupdf  # PyMuPDF
    except ImportError:
        return ""
    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            return "\n".join(page.get_text("text", sort=True) for page in doc).strip()
    except Exception as e:
        logger.warning("PyMuPDF could not read the PDF: %s", type(e).__name__)
        return ""


def _pdf_page_images(file_bytes: bytes, max_pages: int = MAX_OCR_PAGES) -> List[str]:
    """Render the first pages as small base64 JPEGs (kept under ~170 KB for the vision API)."""
    import base64
    try:
        import pymupdf
    except ImportError:
        return []
    images = []
    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            for page in list(doc)[:max_pages]:
                for dpi, quality in ((110, 70), (90, 60), (72, 50)):
                    pix = page.get_pixmap(dpi=dpi)
                    data = pix.tobytes("jpeg", jpg_quality=quality)
                    if len(data) * 4 / 3 < 170_000:
                        break
                images.append(base64.b64encode(data).decode())
    except Exception as e:
        logger.warning("Could not render PDF pages: %s", type(e).__name__)
        return []
    return images


_OCR_ENGINE = None


def _ocr_engine():
    """Local OCR (RapidOCR, ONNX, runs on CPU in ~1-2 s per page). Returns a callable or None."""
    global _OCR_ENGINE
    if _OCR_ENGINE is not None:
        return _OCR_ENGINE or None
    try:
        from rapidocr import RapidOCR  # rapidocr >= 2 (supports Python 3.13)
        engine = RapidOCR()

        def run(img: bytes):
            res = engine(img)
            boxes, txts, scores = getattr(res, "boxes", None), getattr(res, "txts", None), getattr(res, "scores", None)
            if boxes is None or txts is None:
                return []
            return [(b, t, s) for b, t, s in zip(boxes, txts, scores if scores is not None else [1.0] * len(txts))]
        _OCR_ENGINE = run
    except ImportError:
        try:
            from rapidocr_onnxruntime import RapidOCR  # older package name
            engine = RapidOCR()

            def run(img: bytes):
                result, _ = engine(img)
                return [(r[0], r[1], r[2]) for r in (result or [])]
            _OCR_ENGINE = run
        except ImportError:
            _OCR_ENGINE = False
    except Exception as e:  # model files missing, onnxruntime problem, ...
        logger.warning("Local OCR could not start: %s", e)
        _OCR_ENGINE = False
    return _OCR_ENGINE or None


def order_ocr_lines(items, page_width: float) -> str:
    """Turn OCR boxes into reading-order text. Two-column CV layouts are read column by column."""
    rows = []
    for box, txt, score in items:
        txt = str(txt or "").strip()
        if not txt or (score is not None and float(score) < 0.5):
            continue
        xs = [float(pt[0]) for pt in box]; ys = [float(pt[1]) for pt in box]
        rows.append({"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys), "t": txt})
    if not rows:
        return ""
    width = max(page_width, max(r["x1"] for r in rows)) or 1.0
    bins = 100
    cov = [0] * bins
    for r in rows:
        for b in range(int(r["x0"] / width * bins), min(bins - 1, int(r["x1"] / width * bins)) + 1):
            cov[b] += 1
    limit = max(1, int(len(rows) * 0.05))
    best, start = None, None
    for b in range(20, 81):
        if cov[b] <= limit:
            start = b if start is None else start
        else:
            if start is not None and (best is None or b - start > best[1]):
                best = (start, b - start)
            start = None
    if start is not None and (best is None or 81 - start > best[1]):
        best = (start, 81 - start)
    columns = [rows]
    if best and best[1] >= 2:
        split = (best[0] + best[1] / 2) / bins * width
        left = [r for r in rows if (r["x0"] + r["x1"]) / 2 < split]
        right = [r for r in rows if (r["x0"] + r["x1"]) / 2 >= split]
        if len(left) >= 3 and len(right) >= 3:
            columns = [left, right]
    out = []
    for col in columns:
        col.sort(key=lambda r: r["y0"])
        lines = []
        for r in col:
            cy, h = (r["y0"] + r["y1"]) / 2, max(1.0, r["y1"] - r["y0"])
            if lines and abs(lines[-1]["cy"] - cy) < max(h, lines[-1]["h"]) * 0.5:
                lines[-1]["items"].append(r)
            else:
                lines.append({"cy": cy, "h": h, "items": [r]})
        out.extend(" ".join(i["t"] for i in sorted(ln["items"], key=lambda i: i["x0"])) for ln in lines)
        out.append("")
    return "\n".join(out).strip()


def _ocr_pdf_local(file_bytes: bytes, max_pages: int = MAX_OCR_PAGES) -> Optional[str]:
    """OCR the first pages on this computer. Returns None if local OCR is not installed."""
    try:
        engine = _ocr_engine()
    except Exception as e:
        logger.warning("Local OCR could not start: %s", e)
        engine = None
    if engine is None:
        return None
    try:
        import pymupdf
    except ImportError:
        return None
    pages = []
    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            for i, page in enumerate(list(doc)[:max_pages]):
                pix = page.get_pixmap(dpi=150)
                with tool_call("ocr:rapidocr", f"read page {i + 1} locally") as t:
                    items = engine(pix.tobytes("png"))
                    text = order_ocr_lines(items, pix.width)
                    t["summary"] = f"page {i + 1}: {len(text)} characters"
                pages.append(text)
    except Exception as e:
        logger.warning("Local OCR failed: %s", e)
        run_warn(f"Local OCR failed ({type(e).__name__}); trying the vision model instead.")
        return None
    return "\n\n".join(p for p in pages if p)


def _ocr_pdf_with_vision(file_bytes: bytes) -> str:
    from concurrent.futures import ThreadPoolExecutor
    import contextvars
    from .nvidia_llm import LLMError, call_nvidia_vision_ocr
    images = _pdf_page_images(file_bytes)
    if not images:
        return ""
    run_warn(f"The PDF has no readable text layer (design tool or scan); reading {len(images)} page image(s) with the NVIDIA vision model.")

    def read(i_img):
        i, img = i_img
        try:
            return call_nvidia_vision_ocr(img, page_label=f"page {i + 1}")
        except LLMError as e:
            run_warn(f"Vision model could not read page {i + 1}: {e}")
            return ""
    ctx = contextvars.copy_context()  # keep the dashboard run attached in worker threads
    with ThreadPoolExecutor(max_workers=len(images)) as pool:
        pages = list(pool.map(lambda x: ctx.copy().run(read, x), enumerate(images)))
    return "\n\n".join(p.strip() for p in pages if p and p.strip())


def _docx_text(file_bytes: bytes) -> str:
    doc = docx.Document(io.BytesIO(file_bytes))
    parts = [p.text for p in doc.paragraphs if p.text]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(dict.fromkeys(cells)))
    for section in doc.sections:
        for p in list(section.header.paragraphs) + list(section.footer.paragraphs):
            if p.text.strip():
                parts.append(p.text)
    text = "\n".join(parts).strip()
    if len(text) < MIN_TEXT_CHARS:
        # text boxes / shapes (common in designed CV templates) are not in doc.paragraphs
        import re
        xml = doc.element.xml
        boxes = re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", xml)
        alt = " ".join(b for b in boxes if b.strip())
        if len(alt) > len(text):
            text = alt
    return text


def extract_text_from_file_bytes(file_bytes: bytes, filename: str) -> str:
    """Plain text from a PDF, DOCX or text file. Returns "" if nothing readable (never raw bytes)."""
    fn = filename.lower()
    if fn.endswith(".pdf") or file_bytes[:5] == b"%PDF-":
        text = _pdf_text_pymupdf(file_bytes)  # fast; reads most PDFs
        if len(text) < MIN_TEXT_CHARS:
            alt = _pdf_text_pdfminer(file_bytes)
            if len(alt) > len(text):
                text = alt
        if len(text) < MIN_TEXT_CHARS:
            ocr = _ocr_pdf_local(file_bytes)
            if ocr is None:
                run_warn("Local OCR is not installed (pip install rapidocr onnxruntime); using the slower NVIDIA vision model.")
                ocr = _ocr_pdf_with_vision(file_bytes)
            elif len(ocr) < MIN_TEXT_CHARS:
                run_warn("Local OCR found very little text; trying the NVIDIA vision model as well.")
                ocr = max(ocr, _ocr_pdf_with_vision(file_bytes), key=len)
            if len(ocr) > len(text):
                text = ocr
        return text
    if fn.endswith(".docx"):
        try:
            return _docx_text(file_bytes)
        except Exception as e:
            logger.error("Could not read DOCX %s: %s", filename, type(e).__name__)
            return ""
    if fn.endswith(".doc"):
        run_warn("Old .doc files are not supported; save the CV as .docx or PDF.")
        return ""
    try:
        return file_bytes.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def extract_text_and_profile(file_bytes: bytes, filename: str):
    """Read the document once, then run the CV Agent. Returns (text, extraction)."""
    kind = (filename.rsplit(".", 1)[-1] if "." in filename else "text").lower()
    with tool_call(f"parser:{kind}", f"extract text from {filename}") as t:
        text = extract_text_from_file_bytes(file_bytes, filename)
        t["summary"] = f"{len(text)} characters of text extracted"
    if not text.strip():
        run_warn("No text could be extracted from the document (scanned image or empty file?)")
    return text, ProfileAgent().extract_from_text(text)


def extract_facts_from_bytes(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Extract full structured profile and facts from uploaded document bytes."""
    return extract_text_and_profile(file_bytes, filename)[1]

def confirm_facts(facts: List[Dict], approvals: Dict[str, bool]) -> List[Dict]:
    confirmed = []
    for f in facts:
        key = f.get("path") or f.get("fact_key")
        approved = approvals.get(key, True)
        f["verified"] = approved
        confirmed.append(f)
    return confirmed
