from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from PIL import Image
from pypdf import PdfReader

try:
    import pytesseract
    _PYTESSERACT_INSTALLED = True
except ImportError:
    pytesseract = None
    _PYTESSERACT_INSTALLED = False


class DocumentProcessor:
    IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
    TEXT_SUFFIXES = {".txt", ".md", ".csv"}

    def __init__(self, upload_dir: Path) -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, filename: str, content: bytes) -> Path:
        safe_name = Path(filename or "upload.bin").name
        timestamp = int(time.time())
        target = self.upload_dir / f"{timestamp}_{safe_name}"
        target.write_bytes(content)
        return target

    def extract_document(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            text = self._extract_pdf_text(path)
        elif suffix in self.IMAGE_SUFFIXES:
            text = self._extract_image_text(path)
        elif suffix in self.TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError("Unsupported file type. Use PDF, image, text, or CSV files.")

        cleaned_text = text.strip()
        if not cleaned_text:
            raise ValueError("I could not extract readable text from that document.")

        return {
            "file_name": path.name,
            "file_path": str(path),
            "file_type": suffix.lstrip("."),
            "text": cleaned_text,
            "preview": cleaned_text[:2000],
        }

    @staticmethod
    def _extract_pdf_text(path: Path) -> str:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(page for page in pages if page.strip())

    @staticmethod
    def _extract_image_text(path: Path) -> str:
        if not _PYTESSERACT_INSTALLED:
            return "[OCR unavailable — pytesseract not installed. Run: pip install pytesseract]"
        if not shutil.which("tesseract"):
            return "[OCR unavailable — Tesseract binary not found. Run: brew install tesseract]"
        with Image.open(path) as image:
            return pytesseract.image_to_string(image)
