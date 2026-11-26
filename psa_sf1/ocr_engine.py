"""Offline OCR engine wrapper (RapidOCR primary, Tesseract optional fallback)."""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from .models import OCRBlock


class OCREngine:
    """Runs offline OCR on cleaned images and returns positioned text blocks."""

    def __init__(self) -> None:
        self._backend = None
        self._rapid = None
        self._init_backend()

    def _init_backend(self) -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR

            self._rapid = RapidOCR()
            self._backend = "rapidocr"
            return
        except ImportError:
            pass

        try:
            import pytesseract  # noqa: F401

            self._backend = "tesseract"
            return
        except ImportError as exc:
            raise RuntimeError(
                "No OCR backend available. Install 'rapidocr-onnxruntime' (recommended) or 'pytesseract'."
            ) from exc

    @property
    def backend_name(self) -> str:
        return self._backend or "none"

    def extract(self, cleaned_image: np.ndarray) -> Tuple[List[OCRBlock], str]:
        """Run OCR on a cleaned BGR/grayscale image and return (blocks, full_text)."""
        if self._backend == "rapidocr":
            return self._extract_rapidocr(cleaned_image)
        return self._extract_tesseract(cleaned_image)

    def _extract_rapidocr(self, image: np.ndarray) -> Tuple[List[OCRBlock], str]:
        result, _ = self._rapid(image)
        blocks: List[OCRBlock] = []
        if not result:
            return blocks, ""

        for item in result:
            box, text, score = item[0], str(item[1]).strip(), float(item[2])
            if not text:
                continue
            xs = [pt[0] for pt in box]
            ys = [pt[1] for pt in box]
            blocks.append(
                OCRBlock(
                    text=text,
                    confidence=score,
                    x_min=float(min(xs)),
                    y_min=float(min(ys)),
                    x_max=float(max(xs)),
                    y_max=float(max(ys)),
                )
            )

        blocks.sort(key=lambda b: (b.y_center, b.x_min))
        full_text = _blocks_to_lines(blocks)
        return blocks, full_text

    def _extract_tesseract(self, image: np.ndarray) -> Tuple[List[OCRBlock], str]:
        import pytesseract

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        data = pytesseract.image_to_data(binary, output_type=pytesseract.Output.DICT)

        blocks: List[OCRBlock] = []
        n = len(data["text"])
        for i in range(n):
            text = str(data["text"][i]).strip()
            if not text:
                continue
            conf = float(data["conf"][i]) if data["conf"][i] != "-1" else 0.0
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            blocks.append(
                OCRBlock(
                    text=text,
                    confidence=max(0.0, conf / 100.0),
                    x_min=float(x),
                    y_min=float(y),
                    x_max=float(x + w),
                    y_max=float(y + h),
                )
            )

        blocks.sort(key=lambda b: (b.y_center, b.x_min))
        full_text = _blocks_to_lines(blocks)
        return blocks, full_text


def _blocks_to_lines(blocks: List[OCRBlock]) -> str:
    """Group OCR blocks into reading-order text lines."""
    if not blocks:
        return ""

    avg_h = sum(b.height for b in blocks) / len(blocks)
    y_tol = max(10.0, avg_h * 0.6)

    lines: List[List[OCRBlock]] = []
    for block in blocks:
        placed = False
        for line in lines:
            if abs(block.y_center - line[0].y_center) <= y_tol:
                line.append(block)
                placed = True
                break
        if not placed:
            lines.append([block])

    rendered_lines: List[str] = []
    for line in sorted(lines, key=lambda ln: ln[0].y_center):
        line.sort(key=lambda b: b.x_min)
        rendered_lines.append(" ".join(b.text for b in line))

    return "\n".join(rendered_lines)

