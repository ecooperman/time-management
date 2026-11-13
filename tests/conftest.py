"""Tests run against a throwaway SQLite file built by the real migrations, so
they exercise the schema the app actually ships with. DATABASE_URL must be set
(and the schema built) before app.main is imported: it seeds the default
categories as it loads."""
import os
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_db_file.name}"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

_cfg = Config(str(ROOT / "alembic.ini"))
_cfg.set_main_option("script_location", str(ROOT / "migrations"))
command.upgrade(_cfg, "head")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_categories  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    os.unlink(_db_file.name)


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table before each test, then put the default categories back."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    with SessionLocal() as db:
        seed_categories(db)
    yield


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture()
def category(client):
    return client.get("/api/categories").json()[0]
