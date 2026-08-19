"""
The background loop that turns a task's reminder plan (remind_at +
remind_snooze_minutes + remind_max_count on models.Task) into actual push
notifications. Started once from app/main.py's startup event as a plain
asyncio task - no new systemd unit, no new dependency beyond pywebpush
(see app/push.py). Ties the scheduler's lifetime to the app process, which
already auto-restarts via systemd; a missed cycle from a restart costs at
most CHECK_INTERVAL_SECONDS of delay on a reminder, which is fine for this.
"""
import asyncio
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from . import models, push
from .database import SessionLocal

CHECK_INTERVAL_SECONDS = 300


def _is_due(task: models.Task, now: datetime) -> bool:
    if task.remind_at is None or task.remind_at > now:
        return False
    if task.remind_count_sent == 0:
        return True
    if task.remind_max_count is not None and task.remind_count_sent >= task.remind_max_count:
        return False
    if task.remind_snooze_minutes is None:
        return False  # one-shot reminder, already sent
    if task.last_reminded_at is None:
        return True
    return now >= task.last_reminded_at + timedelta(minutes=task.remind_snooze_minutes)


def check_due_reminders(db: Session) -> None:
    now = datetime.utcnow()
    candidates = (
        db.query(models.Task)
        .filter(
            models.Task.status == models.TaskStatus.open,
            models.Task.remind_at.isnot(None),
            models.Task.remind_at <= now,
        )
        .all()
    )
    for task in candidates:
        if not _is_due(task, now):
            continue
        body = (
            "Reminder: this is still on your list."
            if task.remind_count_sent == 0
            else f"Still not done (reminder #{task.remind_count_sent + 1})."
        )
        push.send_push_to_all(db, title=task.title, body=body, url="/")
        task.remind_count_sent += 1
        task.last_reminded_at = now
    db.commit()


async def run_reminder_loop() -> None:
    while True:
        try:
            with SessionLocal() as db:
                check_due_reminders(db)
        except Exception as e:
            # A bad tick (e.g. VAPID not configured yet) shouldn't kill the
            # loop - log and try again next cycle.
            print(f"reminder check failed: {e}")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
