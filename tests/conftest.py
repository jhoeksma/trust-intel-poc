import os
import tempfile

_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_dir}/test.db"
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402

from app.db import Base, engine  # noqa: E402
import app.models  # noqa: E402,F401


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.db import SessionLocal
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
