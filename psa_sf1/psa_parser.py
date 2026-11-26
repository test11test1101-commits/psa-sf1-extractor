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
}


def detect_psa_format(full_text: str) -> Tuple[str, Optional[str]]:
    """Detect whether the document is 2007 or current PSA format.

    Returns (format_label, warning_if_unsupported).
    """
    upper = full_text.upper()
    compact = re.sub(r"\s+", "", upper)

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

    if is_current:
        return "Current (PSA)", None
    if is_2007:
        return "2007 (NSO/PSA)", None
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
        if any(pat.search(b.text) for pat in stop_re):
            # Stop collecting if we hit the next numbered section below the anchor.
            if b.y_center > anchor.y_center + anchor.height * 0.5:
                y_limit = min(y_limit, b.y_min)
            continue
        candidates.append(b)

    return [b for b in candidates if b.y_center < y_limit]


def _filter_subheaders(blocks: List[OCRBlock]) -> List[OCRBlock]:
    """Remove form subheader tokens like (First), (Middle), (Last), (Day), (Month), (Year)."""
    cleaned: List[OCRBlock] = []
    for b in blocks:
        tokens = [t for t in b.text.split() if t.lower().strip(",.;:") not in SUBHEADER_TOKENS]
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


def _format_person_name_blocks(blocks: List[OCRBlock]) -> str:
    """Format blocks ordered left-to-right as (First, Middle, Last) -> 'LAST, FIRST MIDDLE'."""
    filtered = _filter_subheaders(blocks)
    if not filtered:
        return ""

    # Sort by x_min because PSA forms lay out First | Middle | Last left-to-right.
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
    # Assume last word is surname, preceding words are First + Middle.
    last = words[-1].upper()
    first_middle = " ".join(w.upper() for w in words[:-1])
    return f"{last}, {first_middle}"


def _extract_child_name(blocks: List[OCRBlock], full_text: str, page_width: float) -> str:
    anchor = _find_anchor(blocks, [r"\b1[\.\)]?\s*NAME\b"])
    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"\b2[\.\)]?\s*SEX\b", r"\b3[\.\)]?\s*DATE\s*OF\s*BIRTH\b"],
            x_min=0.0,
            x_max=page_width * 0.72,
        )
        # Exclude the anchor text prefix if OCR merged "1. NAME" with something.
        formatted = _format_person_name_blocks(region)
        if formatted:
            return formatted

    # Text-line fallback
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
            stop_patterns=[r"\b3[\.\)]?\s*DATE\s*OF\s*BIRTH\b", r"\b4[\.\)]?\s*PLACE"],
            x_min=max(0.0, anchor.x_min - 40.0),
            x_max=page_width,
        )
        region_text = " ".join(b.text for b in region)
        parsed = _parse_sex_text(region_text)
        if parsed:
            return parsed

    # Text fallback around "2. SEX"
    m = re.search(r"2[\.\)]?\s*SEX([^\n]*(?:\n[^\n]{1,60})?)", full_text, re.IGNORECASE)
    if m:
        parsed = _parse_sex_text(m.group(1))
        if parsed:
            return parsed
    return ""


def _parse_sex_text(text: str) -> str:
    upper = text.upper()
    # Explicit checked markers like [X] Male, X 1 Male, ✓ Female, etc.
    if re.search(r"(?:[X✓✔☑]\s*1?\s*MALE|1\s*MALE\s*[X✓✔☑])", upper):
        return "M"
    if re.search(r"(?:[X✓✔☑]\s*2?\s*FEMALE|2\s*FEMALE\s*[X✓✔☑])", upper):
        return "F"

    # Standalone word (when only the selected sex is printed/typed, e.g., "FEMALE" or "MALE")
    has_male = bool(re.search(r"\bMALE\b", upper))
    has_female = bool(re.search(r"\bFEMALE\b", upper))
    if has_male and not has_female:
        return "M"
    if has_female and not has_male:
        return "F"
    return ""


def _extract_birthdate(blocks: List[OCRBlock], full_text: str) -> str:
    anchor = _find_anchor(blocks, [r"\b3[\.\)]?\s*DATE\s*OF\s*BIRTH\b", r"DATE\s*OF\s*BIRTH"])
    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"\b4[\.\)]?\s*PLACE\s*OF\s*BIRTH\b", r"\b5[\.\)]?\s*TYPE"],
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

    # Pattern 1: DD Month YYYY (standard PSA Form 102 order: Day | Month | Year)
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
    if m:
        day, month_str, year = int(m.group(1)), m.group(2).lower(), m.group(3)
        month = MONTH_MAP.get(month_str)
        if month and 1 <= day <= 31:
            return f"{month}/{day:02d}/{year}"

    # Pattern 2: Month DD YYYY
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2})\s+(\d{4})\b", text)
    if m:
        month_str, day, year = m.group(1).lower(), int(m.group(2)), m.group(3)
        month = MONTH_MAP.get(month_str)
        if month and 1 <= day <= 31:
            return f"{month}/{day:02d}/{year}"

    # Pattern 3: Numeric MM/DD/YYYY or MM-DD-YYYY
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)
        if 1 <= a <= 12 and 1 <= b <= 31:
            return f"{a:02d}/{b:02d}/{year}"
        if 1 <= b <= 12 and 1 <= a <= 31:
            return f"{b:02d}/{a:02d}/{year}"

    return ""


def _extract_mother_maiden_name(blocks: List[OCRBlock], full_text: str) -> str:
    anchor = _find_anchor(blocks, [r"\b7[\.\)]?\s*MAIDEN\s*NAME\b", r"MAIDEN\s*NAME"])
    if anchor:
        region = _collect_region_blocks(
            blocks,
            anchor,
            stop_patterns=[r"\b8[\.\)]?\s*CITIZENSHIP\b", r"\b9[\.\)]?\s*RELIGION\b"],
            x_min=0.0,
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
    # Item 14. NAME (Father) appears well below Item 7. MAIDEN NAME (Mother).
    mother_anchor = _find_anchor(blocks, [r"\b7[\.\)]?\s*MAIDEN\s*NAME\b", r"MAIDEN\s*NAME"])
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
            stop_patterns=[r"\b15[\.\)]?\s*CITIZENSHIP\b", r"\b16[\.\)]?\s*RELIGION\b"],
            x_min=0.0,
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

