import io
import zipfile
from xml.sax.saxutils import escape

from app.sources.cqc import load_cqc, norm_name

HDR = ["Provider ID", "Provider ODS Code", "Provider Name", "Provider Type", "Service / Population Group", "Domain",
       "Latest Rating", "Publication Date", "Report Type"]


def ods(rows):
    def cell(v):
        return f'<table:table-cell office:value-type="string"><text:p>{escape(str(v))}</text:p></table:table-cell>'
    body = "".join("<table:table-row>" + "".join(cell(c) for c in r) + "</table:table-row>" for r in [HDR] + rows)
    xml = ('<?xml version="1.0"?><office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
           'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
           f'<office:body><office:spreadsheet><table:table table:name="README"><table:table-row>{cell("readme")}</table:table-row></table:table>'
           f'<table:table table:name="Providers">{body}</table:table></office:spreadsheet></office:body></office:document-content>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("content.xml", xml)
    return b.getvalue()


def P(pid, ods, name, grp, dom, rating, date="2026-03-31", rtype="Provider", ptype="NHS Healthcare Organisation"):
    return [pid, ods, name, ptype, grp, dom, rating, date, rtype]


KNOWN = {"RAA": "Alpha NHS Foundation Trust", "RBB": "Beta NHS Trust", "RCC": "Gamma NHS Trust"}


def run(rows, **kw):
    return load_cqc("cqc", "01_October_2026_Latest_ratings.ods", ods(rows), known_orgs=kw.get("known", KNOWN), overrides=kw.get("overrides", {}))


def test_norm_name_ignores_punctuation_and_status_words():
    assert norm_name("The Beta NHS Foundation Trust") == norm_name("Beta NHS Trust") == "beta"
    assert norm_name("Barking, Havering & Redbridge University Hospitals NHS Trust") == "barking havering and redbridge university hospitals"


def test_explicit_code_name_match_and_unmatched():
    r = run([
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Overall", "Good"),
        P("1-B", "", "The Beta NHS Trust", "Overall", "Overall", "Requires improvement"),
        P("1-C", "", "Unknown Hospitals NHS Trust", "Overall", "Overall", "Good"),
    ])
    by = {(m["ods_code"], m["metric_code"]): m for m in r.metrics}
    assert by[("RAA", "cqc:overall")]["value"] == 3 and by[("RAA", "cqc:overall")]["quality_flag"] is None
    assert by[("RBB", "cqc:overall")]["value"] == 2 and by[("RBB", "cqc:overall")]["quality_flag"] == "name_match"
    assert not any(m["ods_code"] == "RCC" for m in r.metrics)
    assert r.profile["unmatched_nhs_count"] == 1 and "Unknown Hospitals" in r.profile["unmatched_nhs_providers"][0]
    assert by[("RAA", "cqc:overall")]["period"] == "2026-03" and by[("RAA", "cqc:overall")]["unit"] == "rating"


def test_new_approach_overall_and_key_questions_and_not_rated():
    r = run([
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Overall", "Good", "2019-03-19"),
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Well-led", "Overall", "Outstanding", "2026-02-10"),
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Safe", "Requires improvement"),
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Well-led", "Not Rated"),
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Use of Resources", "Good"),
    ])
    by = {m["metric_code"]: m for m in r.metrics}
    assert by["cqc:overall"]["value"] == 4 and by["cqc:overall"]["period"] == "2026-02"  # newer new-approach rating wins
    assert by["cqc:safe"]["value"] == 2 and by["cqc:use_of_resources"]["value"] == 3
    assert "cqc:well_led" not in by  # Not Rated is not stored


def test_same_day_conflict_takes_lowest_and_flags():
    r = run([P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Overall", "Good"),
             P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Overall", "Requires improvement")])
    m = next(m for m in r.metrics if m["metric_code"] == "cqc:overall")
    assert m["value"] == 2 and m["quality_flag"] == "multiple_ratings"


def test_core_services_and_override_and_non_nhs_ignored():
    r = run([
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Maternity", "Overall", "Inadequate", rtype="CoreService"),
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Urgent and emergency services", "Overall", "Good", rtype="CoreService"),
        P("1-A", "RAA", "Alpha NHS Foundation Trust", "Surgery", "Overall", "Requires improvement", rtype="CoreService"),
        P("1-Z", "", "Weird Name Ltd", "Overall", "Overall", "Good"),
        P("1-S", "", "Alpha Care Home", "Overall", "Overall", "Good", ptype="Social Care Org"),
    ], overrides={"1-Z": "RCC"})
    by = {(m["ods_code"], m["metric_code"]): m["value"] for m in r.metrics}
    assert by[("RAA", "cqc:core_services_rated")] == 3 and by[("RAA", "cqc:core_services_below_good")] == 2
    assert by[("RAA", "cqc:core_services_below_good_pct")] == 66.7
    assert by[("RCC", "cqc:overall")] == 3  # via override
    assert r.profile["matched"] == {"ods_code": 1, "override": 1}


def test_snapshot_store_replaces_same_key(db):
    from sqlalchemy import func, select
    from app.models import Metric, SourceFile
    from app.pipeline import _store
    from app.sources.registry import SOURCES
    spec = SOURCES["cqc"]
    for name in ("01_October_2026_Latest_ratings.ods", "01_November_2026_Latest_ratings.ods"):
        res = load_cqc("cqc", name, ods([P("1-A", "RAA", "Alpha NHS Foundation Trust", "Overall", "Overall", "Good")]), known_orgs=KNOWN, overrides={})
        sf = SourceFile(source_key="cqc", file_name=name, status="loading")
        db.add(sf)
        db.flush()
        _store(db, spec, sf, res)
    db.commit()
    rows = db.execute(select(Metric.metric_code, Metric.period, func.count()).group_by(Metric.metric_code, Metric.period)).all()
    assert all(n == 1 for _, _, n in rows)  # same rating, same publication month: one row, not two


def test_provider_id_that_is_an_ods_code_beats_name_and_conflicts_are_reported():
    r = run([P("RAA", "", "Alpha Renamed NHS Foundation Trust", "Overall", "Overall", "Good"),
             P("RCC", "", "Beta NHS Trust", "Overall", "Overall", "Outstanding")])
    by = {m["ods_code"]: m for m in r.metrics if m["metric_code"] == "cqc:overall"}
    assert by["RAA"]["value"] == 3 and by["RAA"]["quality_flag"] is None  # exact join, not a name match
    assert by["RCC"]["value"] == 4  # provider id wins even though the name says RBB
    assert r.profile["matched"] == {"provider_id": 2}
    assert "RCC" in r.profile["provider_id_vs_name_conflicts"][0]


def test_snapshot_month_parsed_from_underscored_file_name():
    r = run([P("RAA", "", "Alpha NHS Foundation Trust", "Maternity", "Overall", "Good", rtype="CoreService")])
    assert {m["period"] for m in r.metrics if m["metric_code"].startswith("cqc:core")} == {"2026-10"}
