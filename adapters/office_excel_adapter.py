from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from artifacts.artifact_manager import ensure_export_dir


def create_excel_workbook(title: str, headers: list[str], rows: list[list], output_name: str) -> Path:
    out_dir = ensure_export_dir()
    path = out_dir / output_name
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31] or "Sheet1"
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
    for row in rows:
        ws.append(row)
    for column in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(max_len + 2, 12), 42)
    wb.save(path)
    return path
