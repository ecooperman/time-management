from datetime import date, datetime, timedelta
from typing import Optional

from shared_python import owned
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models, schemas
from .database import SessionLocal
from .seed import seed_categories


class BadReference(Exception):
    """A request named a category, job or person that is not the signed-in person's (it does not exist for them, or it
    is someone else's: they look exactly the same, on purpose). The routers answer 400."""


class DeviceInUse(Exception):
    """The push endpoint is already registered to another account. The routers answer 409."""


def _must_have(db: Session, model, row_id, what: str) -> None:
    """The signed-in person must own row `row_id` of `model` (the data layer only shows them their own rows)."""
    if row_id is not None and db.query(select(model.id).where(model.id == row_id).exists()).scalar() is not True:
        raise BadReference(f"That {what} doesn't exist")


def apply_rollover(db: Session) -> None:
    """Push any open task whose scheduled_date is before today forward to today.

    This runs on read (rather than on a background schedule) because the app
    isn't expected to be running continuously - it needs to self-correct
    whenever it's next opened, no matter how many days it sat closed.

    Recurring tasks are excluded - both the origin (repeat_daily=True) and
    its materialized occurrences (series_id set). Rolling either forward
    would land it on a day that already has (or will get) its own
    materialized occurrence, producing a duplicate. An unfinished recurring
    occurrence just stays on its original day, which is also the correct
    "each day is independent" behavior for a daily chore.
    """
    today = datetime.now().date()
    open_tasks = (
        db.query(models.Task)
        .filter(models.Task.status == models.TaskStatus.open)
        .filter(models.Task.scheduled_date.isnot(None))
        .filter(models.Task.repeat_daily.is_(False))
        .filter(models.Task.series_id.is_(None))
        .all()
    )
    changed = False
    for task in open_tasks:
        if task.scheduled_date.date() < today:
            task.scheduled_date = task.scheduled_date.replace(
                year=today.year, month=today.month, day=today.day
            )
            changed = True
    if changed:
        db.commit()


def get_categories(db: Session):
    return db.query(models.Category).all()


def create_category(db: Session, category: schemas.CategoryCreate):
    db_category = models.Category(**category.model_dump())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def get_category(db: Session, category_id: int):
    return db.query(models.Category).filter(models.Category.id == category_id).first()


def update_category(db: Session, category_id: int, updates: schemas.CategoryUpdate):
    db_category = get_category(db, category_id)
    if db_category is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_category, field, value)
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: int) -> str:
    """Returns 'deleted', 'not_found', or 'in_use'."""
    db_category = get_category(db, category_id)
    if db_category is None:
        return "not_found"
    task_count = db.query(models.Task).filter(models.Task.category_id == category_id).count()
    if task_count > 0:
        return "in_use"
    db.delete(db_category)
    db.commit()
    return "deleted"


def get_people(db: Session):
    return db.query(models.Person).order_by(models.Person.name).all()


def create_person(db: Session, person: schemas.PersonCreate):
    db_person = models.Person(**person.model_dump())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person


def get_person(db: Session, person_id: int):
    return db.query(models.Person).filter(models.Person.id == person_id).first()


def update_person(db: Session, person_id: int, updates: schemas.PersonUpdate):
    db_person = get_person(db, person_id)
    if db_person is None:
        return None
    for field, value in updates.model_dump(exclude_unset=True).items():
        setattr(db_person, field, value)
    db.commit()
    db.refresh(db_person)
    return db_person


def delete_person(db: Session, person_id: int) -> str:
    """Returns 'deleted', 'not_found', or 'in_use'."""
    db_person = get_person(db, person_id)
    if db_person is None:
        return "not_found"
    job_count = db.query(models.Job).filter(models.Job.person_id == person_id).count()
    if job_count > 0:
        return "in_use"
    db.delete(db_person)
    db.commit()
    return "deleted"


def get_jobs(db: Session):
    return db.query(models.Job).order_by(models.Job.applied, models.Job.created_at.desc()).all()


def create_job(db: Session, job: schemas.JobCreate):
    _must_have(db, models.Person, job.person_id, "person")
    db_job = models.Job(**job.model_dump())
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job


def get_job(db: Session, job_id: int):
    return db.query(models.Job).filter(models.Job.id == job_id).first()


def get_jobs_by_ids(db: Session, job_ids: list[int]):
    return db.query(models.Job).filter(models.Job.id.in_(job_ids)).all()


def update_job(db: Session, job_id: int, updates: schemas.JobUpdate):
    db_job = get_job(db, job_id)
    if db_job is None:
        return None
    data = updates.model_dump(exclude_unset=True)
    _must_have(db, models.Person, data.get("person_id"), "person")
    for field, value in data.items():
        setattr(db_job, field, value)
    db.commit()
    db.refresh(db_job)
    return db_job


def import_jobs_from_csv(db: Session, rows: list, person_id: Optional[int] = None) -> schemas.JobImportResult:
    """Bulk-upsert jobs from a scored-jobs CSV export (the job-scoring
    Chrome extension). Matches existing jobs by url: if found, refreshes
    only the scoring fields (tier/summary/matched/gaps/strengths/scored_at/
    jd_text) - applied and everything else stay exactly as they were, since
    re-scoring shouldn't touch your tracked application progress. person_id
    (the Person label) is set on newly-created jobs, and backfilled onto
    existing jobs that don't have one yet (e.g. jobs imported before this
    feature existed) - but never overwrites a job that's already tagged, so
    a later re-import can't silently retag whose job it is. Rows missing a
    url or title are skipped.
    """
    _must_have(db, models.Person, person_id, "person")
    created = updated = skipped = 0
    for row in rows:
        url = (row.get("url") or "").strip()
        if not url:
            skipped += 1
            continue

        scored_at = None
        raw_scored_at = (row.get("scored_at") or "").strip()
        if raw_scored_at:
            try:
                scored_at = datetime.fromisoformat(raw_scored_at.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                scored_at = None

        score_data = {
            "salary": (row.get("salary") or "").strip() or None,
            "tier": (row.get("tier") or "").strip() or None,
            "summary": (row.get("summary") or "").strip() or None,
            "matched": (row.get("matched") or "").strip() or None,
            "gaps": (row.get("gaps") or "").strip() or None,
            "strengths": (row.get("strengths") or "").strip() or None,
            "scored_at": scored_at,
            "jd_text": (row.get("jd_text") or "").strip() or None,
        }

        existing = db.query(models.Job).filter(models.Job.url == url).first()
        if existing:
            for field, value in score_data.items():
                setattr(existing, field, value)
            # Fill in the tag if it's not already set (e.g. a job that
            # predates this feature, or was imported with no one picked), but
            # never overwrite one that's already assigned - if two people's
            # CSVs ever both contain the same URL, whoever's already tagged
            # it keeps it rather than a later re-import silently stealing it.
            if person_id is not None and existing.person_id is None:
                existing.person_id = person_id
            updated += 1
        else:
            title = (row.get("title") or "").strip()
            if not title:
                skipped += 1
                continue
            db.add(
                models.Job(
                    name=title,
                    url=url,
                    company=(row.get("company") or "").strip() or None,
                    person_id=person_id,
                    **score_data,
                )
            )
            created += 1

    db.commit()
    return schemas.JobImportResult(created=created, updated=updated, skipped=skipped)


def delete_job(db: Session, job_id: int) -> str:
    """Returns 'deleted', 'not_found', or 'in_use'."""
    db_job = get_job(db, job_id)
    if db_job is None:
        return "not_found"
    task_count = db.query(models.Task).filter(models.Task.job_id == job_id).count()
    if task_count > 0:
        return "in_use"
    db.delete(db_job)
    db.commit()
    return "deleted"


MAX_DAYS_AHEAD = 800  # about two years


def materialize_recurring(db: Session, start: Optional[datetime], end: Optional[datetime]) -> None:
    """Lazily backfill missing daily occurrences for any recurring series.

    Only ever creates occurrences for today or later - a gap in the past is
    left alone, since there's nothing meaningful to retroactively fill in
    for a day that's already gone. Bounded by whatever range is actually
    being viewed, and by each series' own repeat_until if set.
    """
    if end is None:
        return
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Never fill in further ahead than a calendar could sensibly show: otherwise anyone could ask for a range reaching
    # the year 2100 and have a row made for every day of every recurring task they own.
    end = min(end, today + timedelta(days=MAX_DAYS_AHEAD))
    range_start = max(start, today) if start is not None else today
    if range_start >= end:
        return

    origins = db.query(models.Task).filter(models.Task.repeat_daily.is_(True)).all()
    changed = False
    for origin in origins:
        if origin.scheduled_date is None:
            continue
        series_start = max(origin.scheduled_date, range_start)
        series_end = end
        if origin.repeat_until is not None:
            series_end = min(series_end, origin.repeat_until + timedelta(days=1))
        if series_start >= series_end:
            continue

        existing = {
            row.scheduled_date.date()
            for row in db.query(models.Task.scheduled_date)
            .filter(models.Task.series_id == origin.id)
            .filter(models.Task.scheduled_date >= series_start)
            .filter(models.Task.scheduled_date < series_end)
            .all()
        }
        excluded = {
            date.fromisoformat(s) for s in (origin.excluded_recurrence_dates or "").split(",") if s
        }

        max_order = db.query(func.max(models.Task.sort_order)).scalar() or 0

        d = series_start
        while d < series_end:
            if d.date() != origin.scheduled_date.date() and d.date() not in existing and d.date() not in excluded:
                max_order += 10
                db.add(
                    models.Task(
                        category_id=origin.category_id,
                        job_id=origin.job_id,
                        title=origin.title,
                        description=origin.description,
                        status=models.TaskStatus.open,
                        due_date=d,
                        scheduled_date=d,
                        estimate_minutes=origin.estimate_minutes,
                        is_important=origin.is_important,
                        sort_order=max_order,
                        series_id=origin.id,
                    )
                )
                changed = True
            d += timedelta(days=1)

    if changed:
        db.commit()


def cleanup_future_series_occurrences(db: Session, origin_id: int, bound: Optional[datetime]) -> None:
    """Delete not-yet-passed materialized occurrences of a series that are
    now out of bounds (repeat turned off entirely, or repeat_until pulled
    in). Past occurrences are left alone as historical record.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    query = (
        db.query(models.Task)
        .filter(models.Task.series_id == origin_id)
        .filter(models.Task.scheduled_date >= today)
    )
    if bound is not None:
        query = query.filter(models.Task.scheduled_date > bound)
    deleted = query.delete(synchronize_session=False)
    if deleted:
        db.commit()


def stop_recurrence(db: Session, task_id: int) -> Optional[models.Task]:
    """Ends a recurring series as of the given task's own scheduled_date -
    that task becomes the last one in the series; nothing after it
    continues. Works whether task_id is the origin itself or one of its
    materialized occurrences (the common case this exists for - finding
    and editing the origin days or weeks after a series started is exactly
    the friction this shortcut avoids). Reuses the same repeat_until +
    cleanup_future_series_occurrences mechanics as manually pulling in the
    end date via update_task, just without needing to open the origin at
    all.

    Returns the origin task (which may not be task_id itself), or None if
    the task doesn't exist or isn't part of any recurring series."""
    task = get_task(db, task_id)
    if task is None:
        return None
    if task.repeat_daily:
        origin = task
    elif task.series_id is not None:
        origin = get_task(db, task.series_id)
    else:
        return None
    if origin is None or origin.scheduled_date is None:
        return None

    cutoff = task.scheduled_date
    origin.repeat_until = cutoff
    db.commit()
    db.refresh(origin)
    cleanup_future_series_occurrences(db, origin.id, cutoff)
    return origin


def get_tasks(db: Session, start: Optional[datetime] = None, end: Optional[datetime] = None):
    apply_rollover(db)
    materialize_recurring(db, start, end)
    query = db.query(models.Task).filter(models.Task.scheduled_date.isnot(None))
    if start is not None:
        query = query.filter(models.Task.scheduled_date >= start)
    if end is not None:
        query = query.filter(models.Task.scheduled_date < end)
    return query.order_by(models.Task.sort_order, models.Task.id).all()


def get_backlog(db: Session):
    apply_rollover(db)
    return (
        db.query(models.Task)
        .filter(
            (models.Task.scheduled_date.is_(None))
            | (models.Task.status == models.TaskStatus.on_hold)
        )
        .order_by(models.Task.sort_order, models.Task.id)
        .all()
    )


def create_task(db: Session, task: schemas.TaskCreate):
    _must_have(db, models.Category, task.category_id, "category")
    _must_have(db, models.Job, task.job_id, "job")
    max_order = db.query(func.max(models.Task.sort_order)).scalar() or 0
    db_task = models.Task(**task.model_dump(), sort_order=max_order + 10)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def get_task(db: Session, task_id: int):
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def update_task(db: Session, task_id: int, updates: schemas.TaskUpdate):
    db_task = get_task(db, task_id)
    if db_task is None:
        return None

    data = updates.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"] is None:
        raise BadReference("A task needs a category")
    _must_have(db, models.Category, data.get("category_id"), "category")
    _must_have(db, models.Job, data.get("job_id"), "job")
    was_done = db_task.status == models.TaskStatus.done
    becoming_done = data.get("status") == models.TaskStatus.done

    if becoming_done and not was_done:
        data["completed_at"] = datetime.utcnow()
        if db_task.job_id is not None:
            job = get_job(db, db_task.job_id)
            if job is not None:
                job.applied = True
    elif "status" in data and not becoming_done and was_done:
        # Reopening (or putting on hold) a previously-done task un-does the
        # completion side effect on its linked job, if it has one - and
        # restarts its reminder plan from scratch, same reasoning as below.
        data["completed_at"] = None
        data["remind_count_sent"] = 0
        data["last_reminded_at"] = None
        if db_task.job_id is not None:
            job = get_job(db, db_task.job_id)
            if job is not None:
                job.applied = False

    # Editing any part of the reminder plan restarts it - otherwise raising
    # remind_max_count after it's already been hit (or changing remind_at
    # to a new time) would carry over stale bookkeeping from the old plan.
    if any(field in data for field in ("remind_at", "remind_snooze_minutes", "remind_max_count")):
        data.setdefault("remind_count_sent", 0)
        data.setdefault("last_reminded_at", None)

    if data.get("status") == models.TaskStatus.on_hold:
        data.setdefault("scheduled_date", None)

    old_repeat_daily = db_task.repeat_daily
    old_repeat_until = db_task.repeat_until

    for field, value in data.items():
        setattr(db_task, field, value)

    db.commit()
    db.refresh(db_task)

    # Repeat was turned off, or repeat_until was pulled in - remove any
    # already-materialized future occurrences that are now out of bounds.
    if old_repeat_daily:
        if not db_task.repeat_daily:
            cleanup_future_series_occurrences(db, db_task.id, None)
        elif db_task.repeat_until is not None and (
            old_repeat_until is None or db_task.repeat_until < old_repeat_until
        ):
            cleanup_future_series_occurrences(db, db_task.id, db_task.repeat_until)

    return db_task


def reorder_tasks(db: Session, updates: list[schemas.ReorderItem]):
    tasks_by_id = {t.id: t for t in db.query(models.Task).filter(
        models.Task.id.in_([u.id for u in updates])
    ).all()}
    for update in updates:
        db_task = tasks_by_id.get(update.id)
        if db_task is None:
            continue
        db_task.scheduled_date = update.scheduled_date
        db_task.due_date = update.due_date
        db_task.sort_order = update.sort_order
        if update.scheduled_date is not None and db_task.status == models.TaskStatus.on_hold:
            db_task.status = models.TaskStatus.open
    db.commit()
    return list(tasks_by_id.values())


def delete_task(db: Session, task_id: int):
    db_task = get_task(db, task_id)
    if db_task is None:
        return False
    was_repeating = db_task.repeat_daily

    # Record a tombstone on the origin before deleting a series occurrence,
    # so materialize_recurring's lazy gap-filling never silently recreates
    # a lookalike for this exact date on the next fetch - without this, a
    # deleted today-or-future occurrence of a still-active series would
    # reappear the moment the calendar refreshes (which happens right after
    # every delete). Deleting the origin itself doesn't need this - that
    # already ends the whole series via cleanup_future_series_occurrences
    # below.
    if db_task.series_id is not None and db_task.scheduled_date is not None:
        origin = get_task(db, db_task.series_id)
        if origin is not None:
            excluded = [s for s in (origin.excluded_recurrence_dates or "").split(",") if s]
            date_str = db_task.scheduled_date.date().isoformat()
            if date_str not in excluded:
                excluded.append(date_str)
                origin.excluded_recurrence_dates = ",".join(excluded)

    db.delete(db_task)
    db.commit()
    if was_repeating:
        cleanup_future_series_occurrences(db, task_id, None)
    return True


def upsert_push_subscription(db: Session, subscription: schemas.PushSubscriptionCreate):
    """Keyed by endpoint (the browser assigns a fresh one per subscribe
    call, but re-subscribing the same device can still land on the same
    endpoint) - re-subscribing just refreshes the keys rather than making
    a duplicate row.

    A device belongs to ONE account's reminders and is never taken over: if this endpoint is already registered to
    someone else (a phone or browser two people share) the request is refused. Turning reminders off in the browser
    and on again gives the device a fresh endpoint that can then be registered to the new account."""
    me = owned.current_owner()
    with owned.unscoped(), SessionLocal() as other:  # a separate session: never mix unscoped and scoped work in one
        taken = other.query(models.PushSubscription).filter(
            models.PushSubscription.endpoint == subscription.endpoint, models.PushSubscription.owner_id != me
        ).first()
    if taken is not None:
        raise DeviceInUse("This device is already set up for someone else's reminders. Turn reminders off on this "
                          "device and on again to use it for yours.")
    existing = db.query(models.PushSubscription).filter(
        models.PushSubscription.endpoint == subscription.endpoint
    ).first()
    if existing:
        existing.p256dh = subscription.keys.p256dh
        existing.auth = subscription.keys.auth
        db.commit()
        return existing
    db_subscription = models.PushSubscription(
        endpoint=subscription.endpoint,
        p256dh=subscription.keys.p256dh,
        auth=subscription.keys.auth,
    )
    db.add(db_subscription)
    db.commit()
    db.refresh(db_subscription)
    return db_subscription


def delete_push_subscription_by_endpoint(db: Session, endpoint: str) -> bool:
    result = db.query(models.PushSubscription).filter(models.PushSubscription.endpoint == endpoint).delete()
    db.commit()
    return result > 0


def get_push_subscriptions(db: Session):
    return db.query(models.PushSubscription).all()


# --- accounts ---------------------------------------------------------------------------------------------------------
# The users table is not an owned table (it is how ownership is decided), so these are the only queries that run
# without a person in scope, apart from seeding a new account's default categories (inside THEIR scope).

LEGACY_OWNER_EMAIL = "legacy-owner@time.invalid"


def normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == normalize_email(email)).first()


def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()


def list_users(db: Session):
    return db.query(models.User).filter(models.User.email != LEGACY_OWNER_EMAIL).order_by(func.lower(models.User.email)).all()


def _seed_new_account(db: Session, user) -> None:
    with owned.scope(user.id):
        seed_categories(db)


def adopt_or_create_admin(db: Session, email: str):
    """An administrator's account, made the first time they sign in. If the data that existed before accounts is
    still parked on the placeholder, they take it over by giving it their email: it all becomes theirs without a
    single row moving."""
    email = normalize_email(email)
    existing = get_user_by_email(db, email)
    if existing is not None:
        return existing
    legacy = db.query(models.User).filter(models.User.email == LEGACY_OWNER_EMAIL).first()
    if legacy is not None:
        legacy.email = email
        user = legacy
        db.commit()
    else:
        user = models.User(email=email)
        db.add(user)
        db.commit()
        _seed_new_account(db, user)
    return user


def add_user(db: Session, email: str):
    """Let someone in (an administrator's decision). Returns (user, changed): a person whose access was removed is
    restored, and someone who already has access is left as they are."""
    email = normalize_email(email)
    user = get_user_by_email(db, email)
    if user is not None:
        restored = user.status != models.USER_ACTIVE
        user.status = models.USER_ACTIVE
        db.commit()
        return user, restored
    user = models.User(email=email)
    db.add(user)
    db.commit()
    _seed_new_account(db, user)
    return user, True


def set_user_status(db: Session, user, status: str):
    user.status = status
    db.commit()
    return user


def delete_user_data(db: Session, user_id: int) -> dict:
    """Permanently delete everything a person owns. Runs inside THEIR scope (never anyone else's), children first."""
    counts = {}
    with owned.scope(user_id):
        for key, model in (("tasks", models.Task), ("reminder_devices", models.PushSubscription), ("jobs", models.Job),
                           ("people", models.Person), ("categories", models.Category)):
            counts[key] = db.query(model).delete(synchronize_session=False)
        db.commit()
    return counts
