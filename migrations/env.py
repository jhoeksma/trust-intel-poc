from alembic import context
from sqlalchemy import create_engine, pool

from app.config import settings
from app.db import Base
import app.models  # noqa: F401  (register tables)

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
