"""
Document ingestion pipeline.
Handles PDF / TXT / MD / scanned images -> text extraction -> chunking.

OCR fallback:
- If a PDF page yields near-zero extractable text (i.e. it's a scanned page /
  photographed manual page), the page is rasterized and run through Tesseract OCR.
- Standalone images (photos of handwritten maintenance logs, nameplates,
  equipment manuals, etc.) are OCR'd directly.
- All OCR steps are wrapped in try/except so the pipeline degrades gracefully
  (keeps whatever text was found, flags ocr=False) if tesseract / poppler
  system binaries or the optional Python packages aren't installed.
"""
import re
import uuid
from pathlib import Path
from typing import List, Dict

from pypdf import PdfReader

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}
OCR_MIN_CHARS = 25  # below this, treat a PDF page as "scanned" and try OCR


def _ocr_pil_image(pil_image) -> str:
    try:
        import pytesseract
        return pytesseract.image_to_string(pil_image) or ""
    except Exception:
        return ""


def extract_text(file_path: Path) -> List[Dict]:
    """Returns a list of {page_number, text, ocr} dicts."""
    suffix = file_path.suffix.lower()
    pages: List[Dict] = []

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))
        needs_ocr = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({"page_number": i + 1, "text": text, "ocr": False})
            if len(text.strip()) < OCR_MIN_CHARS:
                needs_ocr.append(i)

        if needs_ocr:
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(str(file_path))
                for i in needs_ocr:
                    if i < len(images):
                        ocr_text = _ocr_pil_image(images[i])
                        if len(ocr_text.strip()) > len(pages[i]["text"].strip()):
                            pages[i]["text"] = ocr_text
                            pages[i]["ocr"] = True
            except Exception:
                # No poppler/pdf2image available — silently keep native text.
                pass

    elif suffix in IMAGE_SUFFIXES:
        # Scanned equipment manuals, handwritten maintenance-log photos, nameplates, etc.
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                text = _ocr_pil_image(img)
        except Exception:
            text = ""
        pages.append({"page_number": 1, "text": text, "ocr": True})

    else:  # txt, md, log, csv-as-text, etc.
        text = file_path.read_text(errors="ignore")
        pages.append({"page_number": 1, "text": text, "ocr": False})

    return pages


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    """Simple sliding-window chunking on whitespace-normalized text."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        # try not to cut mid-word
        if end < len(text):
            last_space = text.rfind(" ", start, end)
            if last_space > start:
                end = last_space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap

    return chunks


def process_document(file_path: Path, doc_id: str, doc_name: str, doc_type: str) -> List[Dict]:
    """
    Full ingestion for one document -> list of chunk records ready for indexing.
    Each record: {chunk_id, doc_id, doc_name, doc_type, page_number, text, source_ocr}
    """
    pages = extract_text(file_path)
    records = []
    for page in pages:
        chunks = chunk_text(page["text"])
        for c in chunks:
            records.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "doc_name": doc_name,
                "doc_type": doc_type,
                "page_number": page["page_number"],
                "text": c,
                "source_ocr": page.get("ocr", False),
            })
    return records
