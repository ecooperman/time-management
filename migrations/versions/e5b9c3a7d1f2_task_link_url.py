"""tasks get a plain link_url; backfilled from each task's linked job

Jobs moved to the resume app (2026-11-20), so a task no longer points at a row in the jobs table. A task that was linked to a job keeps a plain
link to that job's posting instead. The jobs and people tables and tasks.job_id are left in place, unused, as a record.

Revision ID: e5b9c3a7d1f2
Revises: d4a8c2e6f1b3
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5b9c3a7d1f2"
down_revision: Union[str, Sequence[str], None] = "d4a8c2e6f1b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("link_url", sa.String(), nullable=True))
    op.execute("UPDATE tasks SET link_url = (SELECT jobs.url FROM jobs WHERE jobs.id = tasks.job_id) WHERE job_id IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("tasks", schema=None) as batch_op:
        batch_op.drop_column("link_url")
