"""initial schema

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("ods_code", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(300)),
        sa.Column("org_type", sa.String(60)),
        sa.Column("current_code", sa.String(10)),
        sa.Column("first_seen_source", sa.String(60)),
    )
    op.create_table(
        "source_files",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.String(40), index=True),
        sa.Column("page_url", sa.Text),
        sa.Column("file_url", sa.Text),
        sa.Column("file_name", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("size_bytes", sa.BigInteger),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("mapper_status", sa.String(30)),
        sa.Column("error", sa.Text),
        sa.Column("row_count", sa.Integer),
        sa.Column("metric_rows", sa.Integer),
        sa.Column("profile", sa.JSON),
        sa.Column("licence", sa.String(200)),
    )
    op.create_table(
        "metrics",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ods_code", sa.String(10), nullable=False),
        sa.Column("source_key", sa.String(40), nullable=False),
        sa.Column("metric_code", sa.String(200), nullable=False),
        sa.Column("metric_label", sa.String(400)),
        sa.Column("period", sa.String(30), nullable=False),
        sa.Column("period_sort", sa.Integer, nullable=False),
        sa.Column("period_type", sa.String(10), nullable=False),
        sa.Column("value", sa.Float),
        sa.Column("unit", sa.String(20)),
        sa.Column("source_file_id", sa.Integer, sa.ForeignKey("source_files.id", ondelete="SET NULL")),
        sa.Column("quality_flag", sa.String(60)),
    )
    op.create_index("ix_metrics_org_code", "metrics", ["ods_code", "metric_code"])
    op.create_index("ix_metrics_source_period", "metrics", ["source_key", "period_sort"])
    op.create_index("ix_metrics_file", "metrics", ["source_file_id"])
    op.create_table(
        "trust_systems",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ods_code", sa.String(10), index=True),
        sa.Column("category", sa.String(80)),
        sa.Column("supplier", sa.String(200)),
        sa.Column("product", sa.String(200)),
        sa.Column("contract_end", sa.Date),
        sa.Column("note", sa.Text),
        sa.Column("loaded_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "refresh_runs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20)),
        sa.Column("trigger", sa.String(30)),
        sa.Column("summary", sa.JSON),
        sa.Column("log", sa.Text),
    )


def downgrade() -> None:
    for t in ("refresh_runs", "trust_systems", "metrics", "source_files", "orgs"):
        op.drop_table(t)
