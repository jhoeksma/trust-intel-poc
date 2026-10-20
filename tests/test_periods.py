from app.periods import parse_period


def test_quarter():
    p = parse_period("Q1 2026/27")
    assert (p.label, p.sort, p.kind) == ("Q1 2026/27", 202604, "quarter")


def test_quarter_q4_rolls_year():
    assert parse_period("Q4 2025/26").sort == 202601


def test_financial_year():
    p = parse_period("ERIC - 2024_25 - Trust data.csv")
    assert (p.label, p.kind) == ("2024/25", "year")


def test_bad_year_pair_not_a_year():
    assert parse_period("2024/30") is None


def test_iso_and_named_month():
    assert parse_period("2026-04").label == "2026-04"
    assert parse_period("RTT-April-2026").label == "2026-04"
    assert parse_period("Apr26").sort == 202604


def test_none():
    assert parse_period("hello") is None and parse_period(None) is None
