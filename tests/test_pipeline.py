from sqlalchemy import func, select

from app import pipeline
from app.models import Metric, SourceFile
from app.sources.discover import DiscoveredFile, DiscoveryResult

CSV = (b"Quarter,Trust_type,Trust_code,Trust_name,Metric_ID,Metric_description,Units,Value,Rank\n"
       b"Q1 2026/27,Acute trust,RXX,Alpha,OF5200,Adjusted segment,segment,2,\n")


def _patch(monkeypatch, payload):
    monkeypatch.setattr(pipeline, "discover", lambda spec: DiscoveryResult(
        files=[DiscoveredFile(url="https://x/test.csv", text="t", page_url="p", via="discovered")]))
    monkeypatch.setattr(pipeline.fetch, "download", lambda url: payload)


def test_load_then_unchanged_then_changed(db, monkeypatch):
    _patch(monkeypatch, CSV)
    s = pipeline.run_source(db, "nof")
    assert s["loaded"] == 1
    s = pipeline.run_source(db, "nof")
    assert s["unchanged"] == 1 and s["loaded"] == 0
    _patch(monkeypatch, CSV.replace(b",2,\n", b",3,\n"))
    pipeline.run_source(db, "nof")
    assert db.scalar(select(func.count()).select_from(Metric).where(Metric.metric_code.not_in(["nof:peer_group", "nof:peer_subtype"]))) == 1  # replaced, not duplicated
    assert db.scalar(select(Metric.value).where(Metric.metric_code.not_in(["nof:peer_group", "nof:peer_subtype"]))) == 3


def test_discovery_failure_is_recorded(db, monkeypatch):
    monkeypatch.setattr(pipeline, "discover", lambda spec: DiscoveryResult(notes=["boom"]))
    s = pipeline.run_source(db, "nof")
    assert s["failed"] == 1
    assert db.scalar(select(SourceFile.status)) == "discovery_failed"


def test_download_failure_is_recorded(db, monkeypatch):
    monkeypatch.setattr(pipeline, "discover", lambda spec: DiscoveryResult(
        files=[DiscoveredFile(url="https://x/a.csv", text="", page_url="", via="seed_url")]))

    def boom(url):
        raise RuntimeError("403")
    monkeypatch.setattr(pipeline.fetch, "download", boom)
    assert pipeline.run_source(db, "nof")["failed"] == 1
    assert db.scalar(select(SourceFile.status)) == "download_failed"


def test_env_override_wins_over_scraping(monkeypatch):
    from app.sources.discover import discover
    from app.sources.registry import SOURCES
    monkeypatch.setenv("SEED_URLS_NOF", "https://example.org/a.csv, https://example.org/b.csv")
    res = discover(SOURCES["nof"], fetch_html=lambda u: (_ for _ in ()).throw(AssertionError("must not scrape")))
    assert [f.url for f in res.files] == ["https://example.org/a.csv", "https://example.org/b.csv"]
    assert res.files[0].via == "override"


def test_empty_page_is_reported(monkeypatch):
    from app.sources.discover import discover
    from app.sources.registry import SOURCES
    monkeypatch.delenv("SEED_URLS_NOF", raising=False)
    res = discover(SOURCES["nof"], fetch_html=lambda u: "<html><title>Just a moment</title></html>")
    assert any("no links" in n for n in res.notes)


def test_reencoded_name_replaces_old_rows(db, monkeypatch):
    from app.pipeline import run_source
    monkeypatch.setattr(pipeline, "discover", lambda spec: DiscoveryResult(
        files=[DiscoveredFile(url="https://x/ERIC%20-%202024_25%20-%20Trust%20data.csv", text="", page_url="", via="seed_url")]))
    payload = b"Trust Code,Trust Name,Energy cost\nRXX,A,1\nRYY,B,2\nRZZ,C,3\n"
    monkeypatch.setattr(pipeline.fetch, "download", lambda url: payload)
    run_source(db, "eric")
    names = {n for (n,) in db.execute(select(SourceFile.file_name))}
    assert names == {"ERIC - 2024_25 - Trust data.csv"}
    # simulate a row loaded by the earlier version under the encoded name, then reload a changed file
    old = SourceFile(source_key="eric", file_name="ERIC%20-%202024_25%20-%20Trust%20data.csv", status="loaded", sha256="x")
    db.add(old)
    db.flush()
    db.add(Metric(ods_code="RXX", source_key="eric", metric_code="eric:energy_cost", period="unknown", period_sort=0,
                  period_type="unknown", value=1, source_file_id=old.id))
    db.commit()
    monkeypatch.setattr(pipeline.fetch, "download", lambda url: payload.replace(b"RXX,A,1", b"RXX,A,9"))
    run_source(db, "eric")
    assert db.scalar(select(func.count()).select_from(Metric).where(Metric.period == "unknown")) == 0


def test_loader_version_bump_forces_reload(db, monkeypatch):
    _patch(monkeypatch, CSV)
    assert pipeline.run_source(db, "nof")["loaded"] == 1
    sf = db.scalars(select(SourceFile).where(SourceFile.status == "loaded")).first()
    sf.profile = dict(sf.profile, loader_version=0)  # pretend an older loader produced it
    db.commit()
    s = pipeline.run_source(db, "nof")
    assert s["loaded"] == 1 and s["unchanged"] == 0
    assert db.scalar(select(func.count()).select_from(Metric).where(Metric.metric_code.not_in(["nof:peer_group", "nof:peer_subtype"]))) == 1


def test_run_report_runs(db, monkeypatch):
    from app.pipeline import run_report
    _patch(monkeypatch, CSV)
    pipeline.run_source(db, "nof")
    text = run_report(db)
    assert "nof:" in text and "duplicate (org, metric, period) keys: 0" in text
