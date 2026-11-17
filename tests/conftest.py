"""Tests run against a throwaway SQLite file built by the real migrations, so
they exercise the schema the app actually ships with. DATABASE_URL must be set
(and the schema built) before app.main is imported."""
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
from shared_python import owned  # noqa: E402
from shared_python import settings as shared_settings  # noqa: E402

from app import config, models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_categories  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    os.unlink(_db_file.name)


@pytest.fixture(autouse=True)
def clean_db():
    """Empty every table, then give the dev user (an administrator locally) an account with the default categories and
    run the test inside THEIR scope: the app keeps every person's data private, so even a test's own database calls
    belong to someone. Use `make_user`, `as_user` and `client_as` (below) to bring in a second person."""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    with owned.unscoped(), SessionLocal() as session:
        dev = models.User(email=config.DEV_USER_EMAIL)
        session.add(dev)
        session.commit()
        dev_id = dev.id
    with owned.scope(dev_id), SessionLocal() as db:
        seed_categories(db)
    with owned.scope(dev_id):
        yield


@pytest.fixture()
def make_user():
    """make_user("bob@example.com") -> the new person's id (an account: they have been let in), with the default
    categories every new account gets."""

    def make(email, status=models.USER_ACTIVE):
        with owned.unscoped(), SessionLocal() as session:
            user = models.User(email=email, status=status)
            session.add(user)
            session.commit()
            user_id = user.id
        with owned.scope(user_id), SessionLocal() as db:
            seed_categories(db)
        return user_id

    return make


@pytest.fixture()
def as_user():
    """`with as_user(person_id) as db:` a fresh database session working as that person (never mixes with another)."""
    from contextlib import contextmanager

    @contextmanager
    def work(person_id):
        with owned.scope(person_id), SessionLocal() as session:
            yield session

    return work


@pytest.fixture()
def client_as():
    """client_as("bob@example.com") -> a client making every request as that person (locally the header says who)."""

    def make(email):
        return TestClient(app, headers={"Cf-Access-Authenticated-User-Email": email})

    return make


@pytest.fixture(autouse=True)
def _local_sign_in(monkeypatch):
    """Whatever sign-in settings the developer's shell has, tests start local, with the dev user as the administrator."""
    for name in (
        "CF_TEAM_DOMAIN", "CF_ACCESS_AUD", "OIDC_ISSUER", "OIDC_JWKS_URL", "OIDC_AUDIENCE", "OIDC_COOKIE", "OIDC_CLIENT_ID",
        "OIDC_CLIENT_SECRET", "OIDC_COOKIE_DOMAIN", "OIDC_RETURN_HOSTS", "OIDC_LOGIN_URL", "OIDC_LOGOUT_RETURN_PATH",
    ):
        monkeypatch.setattr(shared_settings, name, None)
    monkeypatch.setattr(shared_settings, "ENV", "local")


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
