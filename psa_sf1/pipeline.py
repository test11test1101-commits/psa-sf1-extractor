"""End-to-end processing pipeline for PSA documents."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .image_processor import clean_image_for_ocr, load_images_from_file
from .models import PSADocumentRecord
from .ocr_engine import OCREngine
from .psa_parser import parse_psa_document


def process_psa_file(file_path: str | Path, ocr_engine: Optional[OCREngine] = None) -> PSADocumentRecord:
    """Load a .jpg/.pdf PSA file, clean with OpenCV, run OCR, and extract the 5 SF1 fields."""
    engine = ocr_engine or OCREngine()
    path = Path(file_path)

    images = load_images_from_file(path)
    # PSA Certificate of Live Birth is on page 1; if multi-page PDF, use page 1 primarily.
    cleaned = clean_image_for_ocr(images[0])
    blocks, full_text = engine.extract(cleaned)
    return parse_psa_document(path.name, blocks, full_text)

