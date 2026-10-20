"""Minimal streaming reader for OpenDocument spreadsheets (.ods), standard library only.

CQC publishes its ratings as .ods files of 25MB or more, which pandas/odfpy would load
whole. This reads content.xml incrementally and yields one row at a time, expanding
repeated cells and skipping runs of empty trailing rows.
"""
import io
import zipfile
from xml.etree import ElementTree as ET

NS = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
}
T = "{%s}" % NS["table"]
TX = "{%s}" % NS["text"]
OF = "{%s}" % NS["office"]
MAX_REPEAT = 2000  # a repeated empty row/column beyond this is formatting padding, not data


def _cell_text(cell) -> str:
    parts = []
    for p in cell.iter(TX + "p"):
        parts.append("".join(p.itertext()))
    return "\n".join(parts).strip()


def _cell_value(cell):
    vt = cell.get(OF + "value-type")
    if vt in ("float", "percentage", "currency"):
        raw = cell.get(OF + "value")
        try:
            f = float(raw)
            return int(f) if f.is_integer() else f
        except (TypeError, ValueError):
            return _cell_text(cell)
    if vt == "date":
        return cell.get(OF + "date-value") or _cell_text(cell)
    return _cell_text(cell)


def sheet_names(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z, z.open("content.xml") as f:
        return [el.get(T + "name") for _, el in ET.iterparse(f, events=("start",)) if el.tag == T + "table"]


def iter_ods(data: bytes, only_sheet: str | None = None):
    """Yield (sheet_name, row_list) for every non-empty row. Rows keep their cell positions."""
    with zipfile.ZipFile(io.BytesIO(data)) as z, z.open("content.xml") as f:
        sheet = None
        for event, el in ET.iterparse(f, events=("start", "end")):
            if event == "start" and el.tag == T + "table":
                sheet = el.get(T + "name")
            elif event == "end" and el.tag == T + "table-row":
                if only_sheet is None or sheet == only_sheet:
                    row: list = []
                    for c in el:
                        if c.tag not in (T + "table-cell", T + "covered-table-cell"):
                            continue
                        v = _cell_value(c)
                        rep = int(c.get(T + "number-columns-repeated", "1"))
                        row.extend([v] * min(rep, MAX_REPEAT if v == "" else rep))
                    while row and row[-1] == "":
                        row.pop()
                    if row:
                        reps = min(int(el.get(T + "number-rows-repeated", "1")), 1 if len(row) else 0)
                        for _ in range(max(reps, 1)):
                            yield sheet, row
                el.clear()
