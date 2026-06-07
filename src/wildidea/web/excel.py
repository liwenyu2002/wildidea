"""Small XLSX writer for admin exports."""
from __future__ import annotations

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


def build_xlsx(sheet_name: str, headers: list[str], rows: list[list[Any]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _root_rels())
        zf.writestr("xl/workbook.xml", _workbook(sheet_name))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels())
        zf.writestr("xl/styles.xml", _styles())
        zf.writestr("xl/worksheets/sheet1.xml", _worksheet(headers, rows))
    return buffer.getvalue()


def _worksheet(headers: list[str], rows: list[list[Any]]) -> str:
    all_rows = [headers, *rows]
    sheet_rows = []
    for row_index, row in enumerate(all_rows, start=1):
        cells = []
        for col_index, value in enumerate(row, start=1):
            style = ' s="1"' if row_index == 1 else ""
            cells.append(f'<c r="{_cell_ref(row_index, col_index)}" t="inlineStr"{style}><is><t>{_xml_text(value)}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    widths = "".join(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>' for i, width in enumerate(_widths(headers), start=1))
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <cols>{widths}</cols>
  <sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>"""


def _cell_ref(row: int, col: int) -> str:
    letters = ""
    while col:
        col, remainder = divmod(col - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"{letters}{row}"


def _xml_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return escape(text, {'"': "&quot;"})


def _widths(headers: list[str]) -> list[int]:
    long_fields = {"任务", "源现象", "抽象方法", "优势", "落地方案", "失败边界", "反馈内容", "任务错误", "任务配置", "任务平均分", "搜索数据"}
    medium_fields = {"用户邮箱", "方案名称", "抽象方法名"}
    widths = []
    for header in headers:
        if header in long_fields:
            widths.append(48)
        elif header in medium_fields:
            widths.append(28)
        else:
            widths.append(max(12, min(22, len(header) + 6)))
    return widths


def _content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""


def _root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""


def _workbook(sheet_name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{_xml_text(sheet_name)}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>"""


def _workbook_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _styles() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2"><font><sz val="11"/></font><font><b/><sz val="11"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF6E08A"/><bgColor indexed="64"/></patternFill></fill></fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="1" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""
