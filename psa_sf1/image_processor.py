"""OpenCV image cleaning and PDF-to-image conversion for PSA documents."""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg"}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
SUPPORTED_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_PDF_EXTENSIONS


def load_images_from_file(file_path: str | Path, pdf_dpi: int = 250) -> List[np.ndarray]:
    """Load a .jpg/.jpeg or .pdf file into a list of BGR numpy images."""
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        # Use numpy.fromfile + cv2.imdecode so non-ASCII Windows paths work reliably.
        data = np.fromfile(str(path), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Could not decode image file: {path}")
        return [image]

    if ext in SUPPORTED_PDF_EXTENSIONS:
        return _render_pdf_pages(path, dpi=pdf_dpi)

    raise ValueError(f"Unsupported file type '{ext}'. Only .jpg, .jpeg, and .pdf are supported.")


def _render_pdf_pages(pdf_path: Path, dpi: int = 250) -> List[np.ndarray]:
    """Render each page of a PDF to a BGR numpy array using pypdfium2."""
    import pypdfium2 as pdfium

    images: List[np.ndarray] = []
    scale = dpi / 72.0
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            try:
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil().convert("RGB")
                rgb = np.array(pil_image)
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                images.append(bgr)
            finally:
                page.close()
    finally:
        doc.close()

    if not images:
        raise ValueError(f"PDF has no renderable pages: {pdf_path}")
    return images


def clean_image_for_ocr(image: np.ndarray, min_width: int = 2200) -> np.ndarray:
    """Clean a scanned PSA document image using OpenCV for accurate OCR.

    Steps:
    1. Convert to grayscale.
    2. Upscale small scans so fine printed labels and handwritten/dot-matrix text stay sharp.
    3. Denoise while preserving edges.
    4. Deskew slight scanner rotation.
    5. Apply CLAHE local contrast enhancement.
    """
    if image is None or image.size == 0:
        raise ValueError("Empty image provided for cleaning.")

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    height, width = gray.shape[:2]
    if width < min_width:
        scale = min_width / float(width)
        gray = cv2.resize(
            gray,
            (int(width * scale), int(height * scale)),
            interpolation=cv2.INTER_CUBIC,
        )

    deskewed = _deskew(gray)

    # Remove yellow/pink PSA security paper tint & uneven scanner shadows by dividing by local background.
    bg = cv2.GaussianBlur(deskewed, (0, 0), sigmaX=25, sigmaY=25)
    normalized = cv2.divide(deskewed, bg, scale=255)

    # Gentle unsharp mask so small form labels and thin dot-matrix text stay crisp for OCR.
    blurred = cv2.GaussianBlur(normalized, (0, 0), sigmaX=1.2)
    sharpened = cv2.addWeighted(normalized, 1.35, blurred, -0.35, 0)

    clahe = cv2.createCLAHE(clipLimit=1.8, tileGridSize=(8, 8))
    enhanced = clahe.apply(sharpened)

    # Convert back to 3-channel BGR so deep-learning OCR (RapidOCR) and Tesseract both accept it.
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Correct small skew angles (0.5 to 15 degrees) using horizontal form lines."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    min_len = max(80, gray.shape[1] // 10)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=min_len, maxLineGap=20)

    angles: List[float] = []
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):
            dx, dy = int(x2) - int(x1), int(y2) - int(y1)
            if abs(dx) < 20:
                continue
            deg = float(np.degrees(np.arctan2(dy, dx)))
            if -15.0 <= deg <= 15.0:
                angles.append(deg)

    if not angles:
        return gray

    angle = float(np.median(angles))
    if abs(angle) < 0.5 or abs(angle) > 15.0:
        return gray

    h, w = gray.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        gray,
        matrix,
        (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

