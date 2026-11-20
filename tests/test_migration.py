"""The task link migration (jobs moved to the resume app): a task that was linked to a job keeps that job's posting as a plain link, a task with no
job gets none, and the old jobs rows and task.job_id stay where they were; and the migrations still build exactly what the models describe."""
import os
import sqlite3
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app import database

ROOT = Path(__file__).resolve().parent.parent
BEFORE = "d4a8c2e6f1b3"


def migrate(url, action, revision):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    os.environ["DATABASE_URL"] = url  # migrations/env.py reads it
    try:
        getattr(command, action)(cfg, revision)
    finally:
        os.environ["DATABASE_URL"] = str(database.DATABASE_URL)


def test_migrations_build_what_the_models_describe(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    migrate(url, "upgrade", "head")
    with create_engine(url).connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), database.Base.metadata) == []


def test_tasks_linked_to_a_job_get_its_posting_as_a_link_and_nothing_is_lost(tmp_path):
    path = tmp_path / "old.db"
    url = f"sqlite:///{path}"
    migrate(url, "upgrade", BEFORE)
    conn = sqlite3.connect(path)
    owner = conn.execute("select id from users limit 1").fetchone()
    owner = owner[0] if owner else conn.execute("insert into users (email, status) values ('a@example.com', 'active')").lastrowid
    cat = conn.execute("insert into categories (name, color, owner_id) values ('Applying', '#000', ?)", (owner,)).lastrowid
    job = conn.execute("insert into jobs (name, url, applied, owner_id) values ('Analyst', 'https://jobs.example/1', 1, ?)", (owner,)).lastrowid
    linked = conn.execute("insert into tasks (category_id, job_id, title, status, sort_order, is_important, repeat_daily, remind_count_sent, owner_id) values (?, ?, 'Apply to Analyst', 'open', 10, 0, 0, 0, ?)", (cat, job, owner)).lastrowid
    plain = conn.execute("insert into tasks (category_id, title, status, sort_order, is_important, repeat_daily, remind_count_sent, owner_id) values (?, 'Plain', 'open', 20, 0, 0, 0, ?)", (cat, owner)).lastrowid
    conn.commit()
    conn.close()

    migrate(url, "upgrade", "head")
    conn = sqlite3.connect(path)
    assert conn.execute("select link_url, job_id from tasks where id = ?", (linked,)).fetchone() == ("https://jobs.example/1", job)
    assert conn.execute("select link_url from tasks where id = ?", (plain,)).fetchone() == (None,)
    assert conn.execute("select count(*) from jobs").fetchone() == (1,)  # the old rows are only a record now, but they are all still there
    conn.close()

    migrate(url, "downgrade", BEFORE)
    conn = sqlite3.connect(path)
    assert "link_url" not in [row[1] for row in conn.execute("pragma table_info(tasks)")]
    conn.close()
