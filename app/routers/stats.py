"""What the dashboard's stats pages ask this app: for each account, when they were last here and how much they have in the app, as
numbers and dates only (never a task's title or text). Administrators only. The counts run inside `owned.unscoped()` because every
table here is private to its owner: this is the one place everyone's rows are counted together."""
from fastapi import APIRouter, Depends
from shared_python import accounts_gate, owned, usage

from .. import models
from ..database import SessionLocal

router = APIRouter(prefix="/api/admin/stats", tags=["stats"], dependencies=[Depends(accounts_gate.require_admin)])


@router.get("")
def stats():
    with owned.unscoped(), SessionLocal() as db:
        return usage.build(db, models.User, {
            "tasks": usage.per_user(db, models.Task.owner_id, models.Task.created_at),
            "tasks done": usage.per_user(db, models.Task.owner_id, models.Task.completed_at, models.Task.status == models.TaskStatus.done),
            "categories": usage.per_user(db, models.Category.owner_id),
            "people": usage.per_user(db, models.Person.owner_id),
            "devices for reminders": usage.per_user(db, models.PushSubscription.owner_id, models.PushSubscription.created_at),
        })
