from sqlalchemy import func, select

from app import pipeline
from app.models import Metric, SourceFile
from app.sources.discover import DiscoveredFile, DiscoveryResult

CSV = b"Org Code,Org Name,Period,Metric ID,Metric Name,Metric Value\nRXX,Alpha,Q1 2026/27,OF5000,Segment,2\n"


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
    _patch(monkeypatch, CSV.replace(b",2\n", b",3\n"))
    pipeline.run_source(db, "nof")
    assert db.scalar(select(func.count()).select_from(Metric)) == 1  # replaced, not duplicated
    assert db.scalar(select(Metric.value)) == 3


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
