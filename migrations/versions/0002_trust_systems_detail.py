"""trust_systems: detail JSON and category index (FHI master installations file)

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trust_systems", sa.Column("detail", sa.JSON))
    op.create_index("ix_trust_systems_category", "trust_systems", ["category"])


def downgrade() -> None:
    op.drop_index("ix_trust_systems_category", table_name="trust_systems")
    op.drop_column("trust_systems", "detail")
