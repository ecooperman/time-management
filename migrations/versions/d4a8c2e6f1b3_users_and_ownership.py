"""users, and every person's data belongs to one of them

Until now the app was private to its one administrator and nothing in it had an owner. Now several people can have
accounts, each with their own completely private data: users, and an owner on categories, people, jobs, tasks and
push subscriptions.

Everything that exists now is parked on a placeholder user (legacy-owner@time.invalid); the first administrator to
sign in takes the placeholder over by giving it their email (app/crud.py adopt_or_create_admin), so it all becomes
theirs without moving a row.

jobs.owner_id (which Person label a job is tagged with) is renamed person_id, because owner_id is now the account
that owns the row. Category and person names go from unique across the whole table to unique per owner.

Revision ID: d4a8c2e6f1b3
Revises: 62a75f2e5e6d
Create Date: 2026-11-17 10:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4a8c2e6f1b3"
down_revision: Union[str, Sequence[str], None] = "62a75f2e5e6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_OWNER_EMAIL = "legacy-owner@time.invalid"
OWNED = ("categories", "people", "jobs", "tasks", "push_subscriptions")

# SQLite reports the old unnamed UNIQUE constraints only if told how they would have been named, which lets batch mode drop them.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    # The job's Person tag moves out of the way first: owner_id is about to mean "which account owns this row".
    with op.batch_alter_table("jobs", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("fk_jobs_owner_id_people", type_="foreignkey")
        batch_op.alter_column("owner_id", new_column_name="person_id", existing_type=sa.Integer(), existing_nullable=True)
    with op.batch_alter_table("jobs", naming_convention=NAMING) as batch_op:
        batch_op.create_foreign_key("fk_jobs_person_id_people", "people", ["person_id"], ["id"])

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO users (email, status, created_at) VALUES (:email, 'active', :now)"),
        {"email": LEGACY_OWNER_EMAIL, "now": datetime.utcnow()},
    )
    legacy_id = conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": LEGACY_OWNER_EMAIL}).scalar()

    # owner_id starts nullable so the existing rows can be filled in.
    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(f"fk_{table}_owner_id_users", "users", ["owner_id"], ["id"])
        conn.execute(sa.text(f"UPDATE {table} SET owner_id = :owner"), {"owner": legacy_id})

    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_index(f"ix_{table}_owner_id", ["owner_id"])

    for table in ("categories", "people"):
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.drop_constraint(f"uq_{table}_name", type_="unique")
            batch_op.create_unique_constraint(f"uq_{table}_owner_id_name", ["owner_id", "name"])


def downgrade() -> None:
    """Downgrade schema. Fails if two people have a category or person label with the same name (the old schema had
    one table-wide namespace), and everyone's data ends up in one place."""
    for table in ("categories", "people"):
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.drop_constraint(f"uq_{table}_owner_id_name", type_="unique")
            batch_op.create_unique_constraint(f"uq_{table}_name", ["name"])
    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.drop_index(f"ix_{table}_owner_id")
            batch_op.drop_constraint(f"fk_{table}_owner_id_users", type_="foreignkey")
            batch_op.drop_column("owner_id")
    op.drop_table("users")
    with op.batch_alter_table("jobs", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("fk_jobs_person_id_people", type_="foreignkey")
        batch_op.alter_column("person_id", new_column_name="owner_id", existing_type=sa.Integer(), existing_nullable=True)
    with op.batch_alter_table("jobs", naming_convention=NAMING) as batch_op:
        batch_op.create_foreign_key("fk_jobs_owner_id_people", "people", ["owner_id"], ["id"])
