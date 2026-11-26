"""DepEd SF1-style Excel (.xlsx) exporter."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import PSADocumentRecord


SF1_COLUMNS = [
    ("LRN", 16),
    ("NAME\n(Last Name, First Name, Middle Name)", 34),
    ("SEX\n(M/F)", 10),
    ("BIRTH DATE\n(mm/dd/yyyy)", 16),
    ("AGE as of\n1st Friday June", 14),
    ("MOTHER\nTONGUE", 16),
    ("IP\n(Ethnic Group)", 16),
    ("RELIGION", 16),
    ("ADDRESS\n(House #/Street/Sitio/Purok)", 24),
    ("ADDRESS\n(Barangay)", 18),
    ("ADDRESS\n(Municipality/City)", 20),
    ("ADDRESS\n(Province)", 18),
    ("FATHER'S NAME\n(Last Name, First Name, Middle Name)", 32),
    ("MOTHER'S MAIDEN NAME\n(Last Name, First Name, Middle Name)", 32),
    ("GUARDIAN\n(Name)", 24),
    ("GUARDIAN\n(Relationship)", 16),
    ("Contact Number of\nParent or Guardian", 18),
    ("REMARKS", 20),
]


def export_to_sf1_xlsx(records: Iterable[PSADocumentRecord], output_path: str | Path) -> Path:
    """Export extracted PSA records into a clean SF1-style .xlsx workbook.

    Only Name, Sex, Birth Date, Father's Name, and Mother's Maiden Name are populated;
    LRN and all other fields not available on a PSA Birth Certificate are left blank.
    """
    out = Path(output_path)
    wb = Workbook()
    ws = wb.active
    ws.title = "SF1"

    thin = Side(border_style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Title banner (Row 1)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(SF1_COLUMNS))
    title_cell = ws.cell(row=1, column=1, value="School Form 1 (SF1) School Register")
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # Column headers (Row 2)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_font = Font(name="Calibri", size=10, bold=True, color="000000")
    ws.row_dimensions[2].height = 34

    for col_idx, (header, width) in enumerate(SF1_COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Data rows (Row 3+)
    data_font = Font(name="Calibri", size=10)
    for row_idx, rec in enumerate(records, start=3):
        row_values = [
            "",                      # 1. LRN (blank)
            rec.name,                # 2. NAME
            rec.sex,                 # 3. SEX
            rec.birthdate,           # 4. BIRTH DATE
            "",                      # 5. AGE (blank)
            "",                      # 6. MOTHER TONGUE (blank)
            "",                      # 7. IP (blank)
            "",                      # 8. RELIGION (blank)
            "",                      # 9. ADDRESS Street (blank)
            "",                      # 10. ADDRESS Barangay (blank)
            "",                      # 11. ADDRESS Municipality/City (blank)
            "",                      # 12. ADDRESS Province (blank)
            rec.father_name,         # 13. FATHER'S NAME
            rec.mother_maiden_name,  # 14. MOTHER'S MAIDEN NAME
            "",                      # 15. GUARDIAN Name (blank)
            "",                      # 16. GUARDIAN Relationship (blank)
            "",                      # 17. Contact Number (blank)
            "",                      # 18. REMARKS (blank)
        ]
        ws.row_dimensions[row_idx].height = 20
        for col_idx, val in enumerate(row_values, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=val)
            cell.font = data_font
            cell.border = border
            align_h = "center" if col_idx in (3, 4) else "left"
            cell.alignment = Alignment(horizontal=align_h, vertical="center")

    ws.freeze_panes = "A3"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(out))
    return out

