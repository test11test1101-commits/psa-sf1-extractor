"""Parser for Philippine PSA Certificate of Live Birth (2007 and current formats only).

Extracts ONLY:
- Name
- Birthdate
- Sex
- Father's Name
- Mother's Maiden Name
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .models import OCRBlock, PSADocumentRecord


MONTH_MAP = {
    "jan": "01", "january": "01",
    "feb": "02", "february": "02",
    "mar": "03", "march": "03",
    "apr": "04", "april": "04",
    "may": "05",
    "jun": "06", "june": "06",
    "jul": "07", "july": "07",
    "aug": "08", "august": "08",
    "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10",
    "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

SUBHEADER_TOKENS = {
    "(first)", "first", "(middle)", "middle", "(last)", "last",
    "(day)", "day", "(month)", "month", "(year)", "year",
    "first)", "middle)", "last)", "(first", "(middle", "(last",
    "(s)", "(oppiw)", "(oippi)", "(uguod)", "(yess)",
    "name", "birth",
}


def detect_psa_format(full_text: str) -> Tuple[str, Optional[str]]:
    """Detect whether the document is a 2007 or current PSA Certificate of Live Birth.

    Returns (format_label, warning_if_unsupported).
    """
    upper = full_text.upper()
    compact = re.sub(r"\s+", "", upper)

    if "CERTIFICATEOFMARRIAGE" in compact or "FORMNO.97" in compact or "FORMNO97" in compact:
        return (
            "Marriage Cert (Form 97)",
            "Not a Birth Certificate (detected Certificate of Marriage). Please upload a PSA Certificate of Live Birth (2007 or current).",
        )

    if "CERTIFICATEOFDEATH" in compact or "FORMNO.103" in compact or "FORMNO103" in compact:
        return (
            "Death Cert (Form 103)",
            "Not a Birth Certificate (detected Certificate of Death). Please upload a PSA Certificate of Live Birth (2007 or current).",
        )

    if "REVISED1993" in compact or "REV.1993" in compact:
        return "Pre-2007 (1993)", "Unsupported PSA format (1993). Only 2007 or current format is supported."

    is_2007 = any(
        marker in compact
        for marker in ("REVISEDJANUARY2007", "REV.JAN.2007", "JANUARY2007", "NATIONALSTATISTICSOFFICE")
    )
    is_current = any(
        marker in compact
        for marker in ("PHILIPPINESTATISTICSAUTHORITY", "REVISED2016", "PSA")
    )
    has_form_102_fields = (
        ("CERTIFICATEOFLIVEBIRTH" in compact or "MUNICIPALFORMNO.102" in compact or "FORMNO.102" in compact)
        or ("MAIDENNAME" in compact and "DATEOFBIRTH" in compact)
    )

    if is_2007:
        return "2007 (NSO/PSA)", None
    if is_current:
        return "Current (PSA)", None
    if has_form_102_fields:
        return "PSA (2007/Current)", None

    return "Unknown", "Could not confirm 2007 or current PSA Birth Certificate format."


def parse_psa_document(
    source_file: str,
    blocks: List[OCRBlock],
    full_text: str,
) -> PSADocumentRecord:
    """Extract only Name, Birthdate, Sex, Father's Name, and Mother's Maiden Name."""
    fmt, fmt_warning = detect_psa_format(full_text)
    warnings: List[str] = []
    if fmt_warning:
        warnings.append(fmt_warning)
        if fmt.startswith("Marriage Cert") or fmt.startswith("Death Cert"):
            return PSADocumentRecord(
                source_file=source_file,
                format_detected=fmt,
                status="Check",
                warnings=warnings,
            )

    page_width = max((b.x_max for b in blocks), default=1600.0)

    name = _extract_child_name(blocks, full_text, page_width)
    sex = _extract_sex(blocks, full_text, page_width)
    birthdate = _extract_birthdate(blocks, full_text)
    mother_maiden_name = _extract_mother_maiden_name(blocks, full_text)
    father_name = _extract_father_name(blocks, full_text)

    missing = []
    if not name:
        missing.append("Name")
    if not birthdate:
        missing.append("Birthdate")
    if not sex:
        missing.append("Sex")
    if not father_name:
        missing.append("Father's Name")
    if not mother_maiden_name:
        missing.append("Mother's Maiden Name")

    if missing:
        warnings.append(f"Missing/unreadable: {', '.join(missing)}")

    status = "OK" if not warnings else "Check"
    return PSADocumentRecord(
        source_file=source_file,
        name=name,
        birthdate=birthdate,
        sex=sex,
        father_name=father_name,
        mother_maiden_name=mother_maiden_name,
        format_detected=fmt,
        status=status,
        warnings=warnings,
    )


def _find_anchor(blocks: List[OCRBlock], patterns: List[str], min_y: float = 0.0) -> Optional[OCRBlock]:
    """Find the first OCR block matching any regex pattern at or below min_y."""
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    for block in sorted(blocks, key=lambda b: (b.y_center, b.x_min)):
        if block.y_center < min_y:
            continue
        for pat in compiled:
            if pat.search(block.text):
                return block
    return None


def _collect_region_blocks(
    blocks: List[OCRBlock],
    anchor: OCRBlock,
    stop_patterns: List[str],
    x_min: float = 0.0,
    x_max: float = 1e9,
    max_dy: Optional[float] = None,
) -> List[OCRBlock]:
    """Collect OCR blocks below `anchor` until a stop label or max_dy."""
    stop_re = [re.compile(p, re.IGNORECASE) for p in stop_patterns]
    effective_dy = max_dy if max_dy is not None else max(180.0, anchor.height * 6.5)
    candidates: List[OCRBlock] = []
    y_start = anchor.y_max - 2.0
    y_limit = anchor.y_max + effective_dy

    for b in sorted(blocks, key=lambda blk: (blk.y_center, blk.x_min)):
        if b is anchor:
            continue
        if b.y_center < y_start or b.y_center > y_limit:
            continue
        if b.x_center < x_min or b.x_center > x_max:
            continue
        # Ignore single-letter vertical margin labels (C-H-I-L-D, M-O-T-H-E-R, F-A-T-H-E-R).
        if len(b.text.strip()) <= 1 and b.x_max <= anchor.x_min + 5.0:
            continue
        if any(pat.search(b.text) for pat in stop_re):
            if b.y_center > anchor.y_center + anchor.height * 0.5:
                y_limit = min(y_limit, b.y_min)
            continue
        candidates.append(b)

    return [b for b in candidates if b.y_center < y_limit]


def _filter_subheaders(blocks: List[OCRBlock]) -> List[OCRBlock]:
    """Remove form subheader tokens like (First), (Middle), (Last), (Day), (Month), (Year)."""
    cleaned: List[OCRBlock] = []
    for b in blocks:
        tokens = [
            t for t in b.text.split()
            if t.lower().strip(",.;:") not in SUBHEADER_TOKENS
            and not re.fullmatch(r"\([^)]{1,10}\)", t)
        ]
        joined = " ".join(tokens).strip()
        if joined:
            cleaned.append(
                OCRBlock(
                    text=joined,
                    confidence=b.confidence,
                    x_min=b.x_min,
                    y_min=b.y_min,
                    x_max=b.x_max,
                    y_max=b.y_max,
                )
            )
    return cleaned


def _first_value_line(blocks: List[OCRBlock]) -> List[OCRBlock]:
    """Return only the blocks belonging to the first horizontal value line."""
    if not blocks:
        return []
    blocks_sorted = sorted(blocks, key=lambda b: (b.y_center, b.x_min))
    first_y = blocks_sorted[0].y_center
    y_tol = max(16.0, blocks_sorted[0].height * 0.9)
    return [b for b in blocks_sorted if abs(b.y_center - first_y) <= y_tol]


def _format_person_name_blocks(blocks: List[OCRBlock]) -> str:
    """Format blocks ordered left-to-right as (First, Middle, Last) -> 'LAST, FIRST MIDDLE'."""
    filtered = _first_value_line(_filter_subheaders(blocks))
    if not filtered:
        return ""

    filtered.sort(key=lambda b: b.x_min)
    raw = " ".join(b.text for b in filtered)
    return _format_first_middle_last_text(raw)


def _format_first_middle_last_text(raw: str) -> str:
    """Convert 'FIRST MIDDLE LAST' (or already 'LAST, FIRST MIDDLE') to 'LAST, FIRST MIDDLE'."""
    text = re.sub(r"\s+", " ", raw).strip(" ,.;:-_")
    if not text:
        return ""
    if "," in text:
        parts = [p.strip() for p in text.split(",", 1)]
        return f"{parts[0].upper()}, {parts[1].upper()}".strip(", ")

    words = text.split()
    if len(words) == 1:
        return words[0].upper()
    if len(words) == 2:
        return f"{words[1].upper()}, {words[0].upper()}"
    last = words[-1].upper()
    first_middle = " ".join(w.upper() for w in words[:-1])
    return f"{last}, {first_middle}"


def _extract_child_name(blocks: List[OCRBlock], full_text: str, page_width: float) -> str:
    anchor = _find_anchor(blocks, [r"\b1[\.\)]?\s*NAME\b", r"^[1IEL\.\)]*\s*NAME$"])
    if anchor:
        sex_anchor = _find_anchor(blocks, [r"\b2[\.\)]?\s*SEX\b"])
        # Only restrict right boundary if 2. SEX sits on the same horizontal row as 1. NAME.
        same_row_sex = (
            sex_anchor is not None
            and abs(sex_anchor.y_center - anchor.y_center) <= max(30.0, anchor.height * 1.5)
        )
        x_max = min(page_width * 0.72, sex_anchor.x_min - 5.0) if same_row_sex else 1e9
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"^\s*2[\.\)]", r"\b2[\.\)]?\s*SEX\b", r"\b3[\.\)]?\s*DATE\s*OF"],
            x_min=anchor.x_min,
            x_max=x_max,
        )
        formatted = _format_person_name_blocks(region)
        if formatted:
            return formatted

    m = re.search(
        r"1[\.\)]?\s*NAME.*?(?:\(First\).*?\(Last\))?\s*\n([^\n]+)",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        candidate = re.sub(r"\(First\)|\(Middle\)|\(Last\)", "", m.group(1), flags=re.IGNORECASE).strip()
        return _format_first_middle_last_text(candidate)
    return ""


def _extract_sex(blocks: List[OCRBlock], full_text: str, page_width: float) -> str:
    anchor = _find_anchor(blocks, [r"\b2[\.\)]?\s*SEX\b"])
    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"^\s*3[\.\)]", r"^\s*4[\.\)]", r"\b4[\.\)]?\s*PLACE"],
            x_min=max(0.0, anchor.x_min - 40.0),
            x_max=anchor.x_max + 200.0,
        )
        region_text = " ".join(b.text for b in region)
        parsed = _parse_sex_text(region_text)
        if parsed:
            return parsed

    m = re.search(r"2[\.\)]?\s*SEX([^\n]*(?:\n[^\n]{1,60})?)", full_text, re.IGNORECASE)
    if m:
        parsed = _parse_sex_text(m.group(1))
        if parsed:
            return parsed
    return ""


def _parse_sex_text(text: str) -> str:
    upper = text.upper()
    if re.search(r"(?:[X✓✔☑]\s*1?\s*MALE|1\s*MALE\s*[X✓✔☑])", upper):
        return "M"
    if re.search(r"(?:[X✓✔☑]\s*2?\s*FEMALE|2\s*FEMALE\s*[X✓✔☑])", upper):
        return "F"

    has_male = bool(re.search(r"\bMALE\b", upper))
    has_female = bool(re.search(r"\bFEMALE\b", upper))
    if has_male and not has_female:
        return "M"
    if has_female and not has_male:
        return "F"
    return ""


def _extract_birthdate(blocks: List[OCRBlock], full_text: str) -> str:
    anchor = _find_anchor(
        blocks,
        [r"\b3[\.\)]?\s*DATE\s*OF\s*BIRTH\b", r"\b3[\.\)]?\s*DATE\s*OF\b", r"DATE\s*OF\s*BIRTH"],
    )
    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"^\s*4[\.\)]", r"\b4[\.\)]?\s*PLACE", r"^\s*5[\.\)]"],
            x_min=0.0,
            x_max=1e9,
        )
        filtered = _filter_subheaders(region)
        filtered.sort(key=lambda b: b.x_min)
        raw = " ".join(b.text for b in filtered)
        parsed = _normalize_date(raw)
        if parsed:
            return parsed

    m = re.search(
        r"3[\.\)]?\s*DATE\s*OF\s*BIRTH.*?(?:\(Day\).*?\(Year\))?\s*\n([^\n]+)",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        parsed = _normalize_date(m.group(1))
        if parsed:
            return parsed
    return ""


def _normalize_date(raw: str) -> str:
    """Normalize PSA birthdate (Day Month Year or Month Day Year or numeric) to MM/DD/YYYY."""
    text = re.sub(r"[,.;]+", " ", raw)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
    if m:
        day, month_str, year = int(m.group(1)), m.group(2).lower(), m.group(3)
        month = MONTH_MAP.get(month_str)
        if month and 1 <= day <= 31:
            return f"{month}/{day:02d}/{year}"

    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})\b", text)
    if m:
        month_str, day, year = m.group(1).lower(), int(m.group(2)), m.group(3)
        month = MONTH_MAP.get(month_str)
        if month and 1 <= day <= 31:
            return f"{month}/{day:02d}/{year}"

    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= a <= 12 and 1 <= b <= 31:
            return f"{a:02d}/{b:02d}/{year}"
        if 1 <= b <= 12 and 1 <= a <= 31:
            return f"{b:02d}/{a:02d}/{year}"

    return ""


def _extract_mother_maiden_name(blocks: List[OCRBlock], full_text: str) -> str:
    anchor = _find_anchor(
        blocks,
        [r"\b7[\.\)]?\s*MAIDEN\s*NAME\b", r"\b7[\.\)]?\s*MAIDEN\b", r"MAIDEN\s*NAME"],
    )
    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"^\s*8[\.\)]", r"^\s*9[\.\)]", r"\b8[\.\)]?\s*CITIZEN"],
            x_min=anchor.x_min,
            x_max=1e9,
        )
        formatted = _format_person_name_blocks(region)
        if formatted:
            return formatted

    m = re.search(
        r"7[\.\)]?\s*MAIDEN\s*NAME.*?(?:\(First\).*?\(Last\))?\s*\n([^\n]+)",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        candidate = re.sub(r"\(First\)|\(Middle\)|\(Last\)", "", m.group(1), flags=re.IGNORECASE).strip()
        return _format_first_middle_last_text(candidate)
    return ""


def _extract_father_name(blocks: List[OCRBlock], full_text: str) -> str:
    mother_anchor = _find_anchor(
        blocks,
        [r"\b7[\.\)]?\s*MAIDEN\s*NAME\b", r"\b7[\.\)]?\s*MAIDEN\b", r"MAIDEN\s*NAME"],
    )
    min_y = mother_anchor.y_max if mother_anchor else 0.0

    anchor = _find_anchor(blocks, [r"\b14[\.\)]?\s*NAME\b"], min_y=min_y)
    if not anchor:
        father_hdr = _find_anchor(blocks, [r"\bFATHER\b"], min_y=min_y)
        if father_hdr:
            anchor = _find_anchor(blocks, [r"\bNAME\b"], min_y=father_hdr.y_min)

    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"^\s*15[\.\)]", r"^\s*16[\.\)]", r"^\s*19[\.\)]", r"\b15[\.\)]?\s*CITIZEN"],
            x_min=anchor.x_min,
            x_max=1e9,
        )
        formatted = _format_person_name_blocks(region)
        if formatted:
            return formatted

    m = re.search(
        r"14[\.\)]?\s*NAME.*?(?:\(First\).*?\(Last\))?\s*\n([^\n]+)",
        full_text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        candidate = re.sub(r"\(First\)|\(Middle\)|\(Last\)", "", m.group(1), flags=re.IGNORECASE).strip()
        return _format_first_middle_last_text(candidate)
    return ""
