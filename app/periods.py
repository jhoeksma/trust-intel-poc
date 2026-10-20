"""Turn the many ways NHS files write a period into (label, sort_key, type).

sort_key is YYYYMM of the period's start (financial years start in April), so
periods of different kinds order sensibly. Returns None when nothing matches.
"""
import re
from typing import NamedTuple

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_QUARTER = re.compile(r"(?i)\bQ([1-4])\W*(20\d{2})\s*[/_\-]\s*(\d{2,4})\b")
_FY = re.compile(r"\b(20\d{2})\s*[/_\-]\s*(\d{2,4})\b")
_ISO_MONTH = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])\b(?!\s*[/_\-]\s*\d)")
_NAMED_MONTH = re.compile(
    r"(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-_/,]*((?:20)?\d{2})(?!\d)"
)


class Period(NamedTuple):
    label: str
    sort: int
    kind: str  # month | quarter | year


def parse_period(text) -> Period | None:
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None

    m = _QUARTER.search(s)
    if m:
        q, start = int(m.group(1)), int(m.group(2))
        end = m.group(3)[-2:]
        month = 4 + (q - 1) * 3
        year = start
        if month > 12:
            month -= 12
            year += 1
        return Period(f"Q{q} {start}/{end}", year * 100 + month, "quarter")

    m = _FY.search(s)
    if m and int(m.group(2)[-2:]) == (int(m.group(1)) + 1) % 100:
        start = int(m.group(1))
        return Period(f"{start}/{str(start + 1)[-2:]}", start * 100 + 4, "year")

    m = _ISO_MONTH.search(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return Period(f"{y}-{mo:02d}", y * 100 + mo, "month")

    m = _NAMED_MONTH.search(s)
    if m:
        mo = _MONTHS[m.group(1).lower()]
        y = int(m.group(2))
        if y < 100:
            y += 2000
        return Period(f"{y}-{mo:02d}", y * 100 + mo, "month")

    return None
