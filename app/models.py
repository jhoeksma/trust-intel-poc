"""Data model. See docs/DATA_DICTIONARY.md for the plain-English version.

Design: one long "metric store" (`metrics`) so that adding a source means adding
metric codes, not changing the schema. Every row traces back to the file it came
from (`source_files`), which carries the URL, hash and retrieval time.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Org(Base):
    __tablename__ = "orgs"

    ods_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(300))
    org_type: Mapped[str | None] = mapped_column(String(60))  # e.g. Acute, Non-acute, Ambulance
    current_code: Mapped[str | None] = mapped_column(String(10))  # successor, once known
    first_seen_source: Mapped[str | None] = mapped_column(String(60))


class SourceFile(Base):
    __tablename__ = "source_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(40), index=True)
    page_url: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # discovered | seed_url | loaded | unchanged | discovery_failed | download_failed | parse_failed
    status: Mapped[str] = mapped_column(String(30))
    mapper_status: Mapped[str | None] = mapped_column(String(30))  # ok | generic | needs_review
    error: Mapped[str | None] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer)
    metric_rows: Mapped[int | None] = mapped_column(Integer)
    profile: Mapped[dict | None] = mapped_column(JSON)  # field inventory: columns, roles, samples
    licence: Mapped[str | None] = mapped_column(String(200))


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    ods_code: Mapped[str] = mapped_column(String(10))
    source_key: Mapped[str] = mapped_column(String(40))
    metric_code: Mapped[str] = mapped_column(String(200))
    metric_label: Mapped[str | None] = mapped_column(String(400))
    period: Mapped[str] = mapped_column(String(30))  # display label, e.g. 2026-04, Q1 2026/27, 2024/25
    period_sort: Mapped[int] = mapped_column(Integer)  # YYYYMM of period start, for ordering
    period_type: Mapped[str] = mapped_column(String(10))  # month | quarter | year | unknown
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(20))
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("source_files.id", ondelete="SET NULL"))
    quality_flag: Mapped[str | None] = mapped_column(String(60))

    __table_args__ = (
        Index("ix_metrics_org_code", "ods_code", "metric_code"),
        Index("ix_metrics_source_period", "source_key", "period_sort"),
    )


class TrustSystem(Base):
    """FHI installed-systems overlay (trust to supplier). Proprietary: never commit the data."""

    __tablename__ = "trust_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ods_code: Mapped[str] = mapped_column(String(10), index=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True)  # department, e.g. EPR
    supplier: Mapped[str | None] = mapped_column(String(200))
    product: Mapped[str | None] = mapped_column(String(200))
    contract_end: Mapped[datetime | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[dict | None] = mapped_column(JSON)  # version, hosting, contract status, verified date ... (see app/systems.py)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RefreshRun(Base):
    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | ok | partial | failed
    trigger: Mapped[str | None] = mapped_column(String(30))
    summary: Mapped[dict | None] = mapped_column(JSON)
    log: Mapped[str | None] = mapped_column(Text)
