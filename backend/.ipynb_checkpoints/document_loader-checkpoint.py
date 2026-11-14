"""Загрузка ТЗ из байтов: txt / pdf (+OCR) / docx / doc."""
import io
import shutil
import subprocess
import tempfile
from pathlib import Path

from textutils import cyr_ratio, normalize_text


class DocumentError(RuntimeError):
    pass


def _decode_bytes(raw: bytes) -> str:
    import chardet

    enc = (chardet.detect(raw) or {}).get("encoding")
    best, best_r = None, -1.0
    for e in [enc, "utf-8", "utf-8-sig", "cp1251", "koi8-r", "cp866", "latin1"]:
        if not e:
            continue
        try:
            t = raw.decode(e)
        except Exception:
            continue
        r = cyr_ratio(t)
        if r > best_r:
            best, best_r = t, r
        if r >= 0.35:
            return t
    return best if best is not None else raw.decode("utf-8", errors="ignore")


def _ocr_pdf(content: bytes, max_pages: int = 40) -> str:
    import pymupdf as fitz
    import pytesseract
    from PIL import Image

    parts = []
    with fitz.open(stream=content, filetype="pdf") as doc:
        for i in range(min(len(doc), max_pages)):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                t = pytesseract.image_to_string(img, lang="rus+eng")
            except Exception:
                t = pytesseract.image_to_string(img, lang="eng")
            if t.strip():
                parts.append(t)
    return "\n".join(parts)


def _read_pdf(content: bytes) -> str:
    import pymupdf as fitz

    with fitz.open(stream=content, filetype="pdf") as doc:
        text = "\n".join(page.get_text("text") or "" for page in doc)
    if len(text.strip()) < 80 or cyr_ratio(text) < 0.15:  # скан → OCR
        try:
            ocr = _ocr_pdf(content)
            if len(ocr.strip()) > len(text.strip()):
                text = ocr
        except Exception as e:
            if not text.strip():
                raise DocumentError(f"PDF без текстового слоя, OCR не удался: {e!r}")
    return text


def _read_docx(content: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = Document(io.BytesIO(content))
    parts = []
    for child in d.element.body.iterchildren():
        if child.tag.endswith("}p"):
            t = Paragraph(child, d).text
            if t and t.strip():
                parts.append(t)
        elif child.tag.endswith("}tbl"):
            for row in Table(child, d).rows:
                cells = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and t not in cells:  # объединённые ячейки дублируются
                        cells.append(t)
                if cells:
                    parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_doc(content: bytes) -> str:
    def ok(t: str) -> bool:
        return len((t or "").strip()) >= 200 and cyr_ratio(t) >= 0.25

    text = ""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.doc"
        path.write_bytes(content)

        if shutil.which("antiword"):
            r = subprocess.run(["antiword", "-m", "UTF-8.txt", "-w", "0", str(path)],
                               capture_output=True, timeout=120)
            text = r.stdout.decode("utf-8", errors="ignore")
            if ok(text):
                return text
        if shutil.which("catdoc"):
            r = subprocess.run(["catdoc", "-d", "utf-8", str(path)],
                               capture_output=True, timeout=120)
            text = r.stdout.decode("utf-8", errors="ignore")
            if ok(text):
                return text
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if soffice:
            subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "txt:Text",
                            "--outdir", tmp, str(path)], capture_output=True, timeout=180)
            out = Path(tmp) / "input.txt"
            if out.exists():
                t = _decode_bytes(out.read_bytes())
                if ok(t):
                    return t
                text = text or t
    return text


def load_document_bytes(content: bytes, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        text = _read_pdf(content)
    elif ext == ".docx":
        text = _read_docx(content)
    elif ext == ".doc":
        text = _read_doc(content)
    else:
        text = _decode_bytes(content)

    text = normalize_text(text)
    if len(text) < 100 or cyr_ratio(text) < 0.20:
        raise DocumentError(
            f"Не удалось извлечь русский текст из «{filename}» "
            f"(chars={len(text)}, cyr={cyr_ratio(text):.2f}). "
            "Для .doc нужны antiword/catdoc/libreoffice, для сканов — tesseract-ocr-rus."
        )
    return text
