"""Automated tests for PSA Birth Certificate (2007/Current) extraction and SF1 export."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

from psa_sf1.image_processor import clean_image_for_ocr
from psa_sf1.models import OCRBlock, PSADocumentRecord
from psa_sf1.pipeline import process_psa_file
from psa_sf1.psa_parser import parse_psa_document
from psa_sf1.sf1_exporter import SF1_COLUMNS, export_to_sf1_xlsx


def _load_font(size: int, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "arialbd.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "arial.ttf",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _make_synthetic_psa_image(out_path: Path, as_pdf: bool = False) -> Path:
    """Create a realistic synthetic PSA Certificate of Live Birth (Current format) image or PDF."""
    img = Image.new("RGB", (1400, 1800), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    font_lg = _load_font(26, bold=True)
    font_md = _load_font(22, bold=False)
    font_sm = _load_font(17, bold=False)

    draw.text((340, 50), "PHILIPPINE STATISTICS AUTHORITY", fill=(0, 0, 0), font=font_lg)
    draw.text((380, 90), "CERTIFICATE OF LIVE BIRTH", fill=(0, 0, 0), font=font_lg)
    draw.text((60, 130), "Municipal Form No. 102 (Revised 2016)", fill=(0, 0, 0), font=font_sm)

    # 1. NAME & 2. SEX
    draw.rectangle([50, 180, 960, 310], outline=(0, 0, 0), width=2)
    draw.text((65, 190), "1. NAME", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 220), "(First)", fill=(0, 0, 0), font=font_sm)
    draw.text((400, 220), "(Middle)", fill=(0, 0, 0), font=font_sm)
    draw.text((680, 220), "(Last)", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 260), "JUAN", fill=(0, 0, 0), font=font_md)
    draw.text((400, 260), "SANTOS", fill=(0, 0, 0), font=font_md)
    draw.text((680, 260), "DELA CRUZ", fill=(0, 0, 0), font=font_md)

    draw.rectangle([960, 180, 1350, 310], outline=(0, 0, 0), width=2)
    draw.text((975, 190), "2. SEX", fill=(0, 0, 0), font=font_sm)
    draw.text((1000, 240), "X 1 Male", fill=(0, 0, 0), font=font_md)
    draw.text((1170, 240), "2 Female", fill=(0, 0, 0), font=font_md)

    # 3. DATE OF BIRTH
    draw.rectangle([50, 310, 1350, 440], outline=(0, 0, 0), width=2)
    draw.text((65, 320), "3. DATE OF BIRTH", fill=(0, 0, 0), font=font_sm)
    draw.text((140, 350), "(Day)", fill=(0, 0, 0), font=font_sm)
    draw.text((420, 350), "(Month)", fill=(0, 0, 0), font=font_sm)
    draw.text((740, 350), "(Year)", fill=(0, 0, 0), font=font_sm)
    draw.text((140, 390), "15", fill=(0, 0, 0), font=font_md)
    draw.text((420, 390), "March", fill=(0, 0, 0), font=font_md)
    draw.text((740, 390), "2014", fill=(0, 0, 0), font=font_md)

    # 4. PLACE OF BIRTH
    draw.rectangle([50, 440, 1350, 540], outline=(0, 0, 0), width=2)
    draw.text((65, 450), "4. PLACE OF BIRTH", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 490), "Quezon City, Metro Manila", fill=(0, 0, 0), font=font_md)

    # MOTHER - 7. MAIDEN NAME
    draw.rectangle([50, 580, 1350, 720], outline=(0, 0, 0), width=2)
    draw.text((65, 590), "MOTHER - 7. MAIDEN NAME", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 620), "(First)", fill=(0, 0, 0), font=font_sm)
    draw.text((400, 620), "(Middle)", fill=(0, 0, 0), font=font_sm)
    draw.text((680, 620), "(Last)", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 660), "MARIA", fill=(0, 0, 0), font=font_md)
    draw.text((400, 660), "REYES", fill=(0, 0, 0), font=font_md)
    draw.text((680, 660), "SANTOS", fill=(0, 0, 0), font=font_md)

    # 8. CITIZENSHIP
    draw.rectangle([50, 720, 1350, 810], outline=(0, 0, 0), width=2)
    draw.text((65, 730), "8. CITIZENSHIP", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 765), "Filipino", fill=(0, 0, 0), font=font_md)

    # FATHER - 14. NAME
    draw.rectangle([50, 860, 1350, 1000], outline=(0, 0, 0), width=2)
    draw.text((65, 870), "FATHER - 14. NAME", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 900), "(First)", fill=(0, 0, 0), font=font_sm)
    draw.text((400, 900), "(Middle)", fill=(0, 0, 0), font=font_sm)
    draw.text((680, 900), "(Last)", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 940), "PEDRO", fill=(0, 0, 0), font=font_md)
    draw.text((400, 940), "GARCIA", fill=(0, 0, 0), font=font_md)
    draw.text((680, 940), "DELA CRUZ", fill=(0, 0, 0), font=font_md)

    # 15. CITIZENSHIP
    draw.rectangle([50, 1000, 1350, 1090], outline=(0, 0, 0), width=2)
    draw.text((65, 1010), "15. CITIZENSHIP", fill=(0, 0, 0), font=font_sm)
    draw.text((120, 1045), "Filipino", fill=(0, 0, 0), font=font_md)

    if as_pdf:
        img.save(str(out_path), "PDF", resolution=150.0)
    else:
        # Slight rotation + mild noise to exercise OpenCV deskew & denoise.
        rotated = img.rotate(1.2, fillcolor=(255, 255, 255))
        rotated.save(str(out_path), "JPEG", quality=95)
    return out_path


def test_parser_2007_format_spatial_blocks() -> None:
    blocks = [
        OCRBlock("NATIONAL STATISTICS OFFICE", 0.99, 300, 40, 900, 70),
        OCRBlock("Municipal Form No. 102 (Revised January 2007)", 0.98, 60, 80, 600, 105),
        OCRBlock("1. NAME", 0.99, 60, 140, 200, 165),
        OCRBlock("(First)", 0.98, 100, 175, 180, 195),
        OCRBlock("(Middle)", 0.98, 350, 175, 450, 195),
        OCRBlock("(Last)", 0.98, 650, 175, 730, 195),
        OCRBlock("ANA", 0.99, 100, 205, 170, 235),
        OCRBlock("LOPEZ", 0.99, 350, 205, 450, 235),
        OCRBlock("MENDOZA", 0.99, 650, 205, 800, 235),
        OCRBlock("2. SEX", 0.99, 1050, 140, 1180, 165),
        OCRBlock("FEMALE", 0.99, 1080, 200, 1220, 235),
        OCRBlock("3. DATE OF BIRTH", 0.99, 60, 280, 300, 305),
        OCRBlock("05", 0.99, 120, 340, 160, 370),
        OCRBlock("October", 0.99, 360, 340, 490, 370),
        OCRBlock("2011", 0.99, 680, 340, 760, 370),
        OCRBlock("4. PLACE OF BIRTH", 0.99, 60, 410, 320, 435),
        OCRBlock("7. MAIDEN NAME", 0.99, 60, 520, 280, 545),
        OCRBlock("ELENA", 0.99, 100, 580, 200, 610),
        OCRBlock("CRUZ", 0.99, 350, 580, 440, 610),
        OCRBlock("LOPEZ", 0.99, 650, 580, 760, 610),
        OCRBlock("8. CITIZENSHIP", 0.99, 60, 650, 280, 675),
        OCRBlock("14. NAME", 0.99, 60, 760, 200, 785),
        OCRBlock("CARLOS", 0.99, 100, 820, 220, 850),
        OCRBlock("RAMOS", 0.99, 350, 820, 470, 850),
        OCRBlock("MENDOZA", 0.99, 650, 820, 800, 850),
        OCRBlock("15. CITIZENSHIP", 0.99, 60, 890, 280, 915),
    ]
    full_text = "\n".join(b.text for b in blocks)
    rec = parse_psa_document("sample_2007.jpg", blocks, full_text)

    assert rec.format_detected == "2007 (NSO/PSA)"
    assert rec.name == "MENDOZA, ANA LOPEZ"
    assert rec.sex == "F"
    assert rec.birthdate == "10/05/2011"
    assert rec.mother_maiden_name == "LOPEZ, ELENA CRUZ"
    assert rec.father_name == "MENDOZA, CARLOS RAMOS"
    assert rec.status == "OK"


def test_parser_rejects_1993_format_warning() -> None:
    text = "Municipal Form No. 102 (Revised 1993)\n1. NAME\nJUAN CRUZ"
    rec = parse_psa_document("old_1993.jpg", [], text)
    assert "1993" in rec.format_detected
    assert rec.status == "Check"
    assert any("1993" in w for w in rec.warnings)


def test_parser_flags_marriage_certificate() -> None:
    text = "PHILIPPINE STATISTICS AUTHORITY\nMunicipal Form No. 97\nCERTIFICATE OF MARRIAGE\n1. Name of Contracting Parties"
    rec = parse_psa_document("marriage.jpg", [], text)
    assert "Marriage" in rec.format_detected
    assert rec.status == "Check"
    assert rec.name == ""
    assert any("Certificate of Marriage" in w for w in rec.warnings)


def test_opencv_cleaner_preserves_dimensions() -> None:
    raw = np.full((600, 800, 3), 245, dtype=np.uint8)
    cv2.putText(raw, "PHILIPPINE STATISTICS AUTHORITY", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    cleaned = clean_image_for_ocr(raw, min_width=1600)
    assert cleaned.shape[1] >= 1600
    assert len(cleaned.shape) == 3


def test_sf1_exporter_leaves_non_psa_fields_blank(tmp_path: Path) -> None:
    rec = PSADocumentRecord(
        source_file="juan.jpg",
        name="DELA CRUZ, JUAN SANTOS",
        birthdate="03/15/2014",
        sex="M",
        father_name="DELA CRUZ, PEDRO GARCIA",
        mother_maiden_name="SANTOS, MARIA REYES",
        format_detected="Current (PSA)",
        status="OK",
    )
    out_xlsx = export_to_sf1_xlsx([rec], tmp_path / "sf1_test.xlsx")
    assert out_xlsx.exists()

    wb = load_workbook(out_xlsx)
    ws = wb["SF1"]

    # Check header count and mapped values in row 3
    headers = [ws.cell(row=2, column=i).value for i in range(1, len(SF1_COLUMNS) + 1)]
    assert len(headers) == 18
    assert ws.cell(row=3, column=1).value in (None, "")   # LRN blank
    assert ws.cell(row=3, column=2).value == "DELA CRUZ, JUAN SANTOS"
    assert ws.cell(row=3, column=3).value == "M"
    assert ws.cell(row=3, column=4).value == "03/15/2014"
    assert ws.cell(row=3, column=5).value in (None, "")   # Age blank
    assert ws.cell(row=3, column=13).value == "DELA CRUZ, PEDRO GARCIA"
    assert ws.cell(row=3, column=14).value == "SANTOS, MARIA REYES"
    assert ws.cell(row=3, column=18).value in (None, "")  # Remarks blank


def test_end_to_end_jpg_and_pdf_pipeline(tmp_path: Path) -> None:
    jpg_path = _make_synthetic_psa_image(tmp_path / "psa_sample.jpg", as_pdf=False)
    pdf_path = _make_synthetic_psa_image(tmp_path / "psa_sample.pdf", as_pdf=True)

    jpg_rec = process_psa_file(jpg_path)
    pdf_rec = process_psa_file(pdf_path)

    for rec in (jpg_rec, pdf_rec):
        assert "DELA" in rec.name and "CRUZ" in rec.name
        assert "JUAN" in rec.name
        assert rec.sex == "M"
        assert rec.birthdate == "03/15/2014"
        assert "DELA" in rec.father_name and "CRUZ" in rec.father_name
        assert "PEDRO" in rec.father_name
        assert "SANTOS" in rec.mother_maiden_name
        assert "MARIA" in rec.mother_maiden_name

    out_xlsx = export_to_sf1_xlsx([jpg_rec, pdf_rec], tmp_path / "SF1_Output.xlsx")
    assert out_xlsx.exists()

