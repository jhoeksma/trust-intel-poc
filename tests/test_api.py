import io

import pytest
from fastapi.testclient import TestClient

from app.models import Metric, Org, SourceFile


@pytest.fixture()
def client(db):
    from app.main import app
    sf = SourceFile(source_key="nof", status="loaded")
    db.add(sf)
    db.add_all([Org(ods_code="RXX", name="Alpha Trust"), Org(ods_code="RYY", name="Beta Trust")])
    db.flush()

    def m(org, code, label, period, sort, val, src="nof"):
        return Metric(ods_code=org, source_key=src, metric_code=code, metric_label=label, period=period,
                      period_sort=sort, period_type="quarter", value=val, source_file_id=sf.id)
    db.add_all([
        m("RXX", "nof:of5000", "Adjusted segment", "Q1 2026/27", 202604, 2),
        m("RXX", "nof:of5000", "Adjusted segment", "Q4 2025/26", 202601, 3),
        m("RYY", "nof:of5000", "Adjusted segment", "Q1 2026/27", 202604, 4),
        m("RXX", "rtt:pct_within_18_weeks", "RTT within 18w", "2026-04", 202604, 61.5, "rtt"),
    ])
    db.commit()
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_trust_list_has_strain(client):
    rows = {r["ods_code"]: r for r in client.get("/api/trusts").json()}
    assert rows["RXX"]["strain"] == 2 and rows["RYY"]["strain"] == 4
    assert rows["RXX"]["rtt_pct_18w"] == 61.5


def test_scorecard_latest_and_previous(client):
    card = client.get("/api/trusts/rxx").json()
    seg = next(x for x in card["metrics"] if x["metric_code"] == "nof:of5000")
    assert seg["value"] == 2 and seg["previous_value"] == 3
    assert card["strain"]["score"] == 2


def test_unknown_trust_404(client):
    assert client.get("/api/trusts/ZZZ").status_code == 404


def test_compare(client):
    c = client.get("/api/compare?codes=RXX,RYY").json()
    row = next(r for r in c["rows"] if r["metric_code"] == "nof:of5000")
    assert row["values"]["RXX"]["value"] == 2 and row["values"]["RYY"]["value"] == 4


def test_systems_import_and_join_rate(client):
    csv_data = "ods_code,category,supplier,product,contract_end\nRXX,EPR,Acme,Acme EPR,31/03/2028\nQQQ,EPR,Other,X,2027-01-01\n"
    r = client.post("/api/systems/import", files={"file": ("s.csv", io.BytesIO(csv_data.encode()), "text/csv")})
    body = r.json()
    assert body["imported"] == 2 and body["codes_not_in_public_data"] == ["QQQ"] and body["join_rate"] == 0.5
    card = client.get("/api/trusts/RXX").json()
    assert card["systems"][0]["supplier"] == "Acme" and card["systems"][0]["contract_end"] == "2028-03-31"
    assert next(t for t in client.get("/api/trusts").json() if t["ods_code"] == "RXX")["suppliers"] == ["Acme"]


def test_sources_endpoint(client):
    s = client.get("/api/sources").json()
    assert {x["key"] for x in s["registry"]} >= {"nof", "rtt", "eric", "hes", "workforce"}
    assert s["coverage"][0]["source"] in {"nof", "rtt"}


def test_auth_enforced_when_required(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "basic_auth_user", "u")
    monkeypatch.setattr(settings, "basic_auth_password", "p")
    assert client.get("/api/trusts").status_code == 401
    assert client.get("/api/trusts", auth=("u", "p")).status_code == 200
    assert client.get("/health").status_code == 200


def test_reference_seed_and_coverage(client, db):
    from app.reference import load_reference, seed_orgs
    ref = load_reference()
    assert len(ref) > 200 and all(r["ods_code"] for r in ref) and len({r["ods_code"] for r in ref}) == len(ref)
    assert seed_orgs(db) > 0
    db.add(Metric(ods_code="ZZZ", source_key="x", metric_code="x:a", period="2026-04", period_sort=202604, period_type="month", value=1))
    db.commit()
    cov = client.get("/api/sources").json()["reference_coverage"]
    assert cov["reference_orgs"] == len(ref) and "ZZZ" in cov["public_data_not_in_reference"]


def test_successor_code_history_shows_on_current_trust(client, db):
    from app.reference import load_successors
    assert load_successors().get("RBZ") == "RH8"
    db.add_all([Org(ods_code="RBZ", name="Northern Devon", current_code="RH8"), Org(ods_code="RH8", name="Royal Devon")])
    db.add(Metric(ods_code="RBZ", source_key="rtt", metric_code="rtt:pct_within_18_weeks", period="2021-12", period_sort=202112,
                  period_type="month", value=55.0))
    db.commit()
    card = client.get("/api/trusts/RH8").json()
    assert any(m["metric_code"] == "rtt:pct_within_18_weeks" for m in card["metrics"])
