import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class TaskStatus(str, enum.Enum):
    open = "open"
    done = "done"
    on_hold = "on_hold"


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)

    tasks = relationship("Task", back_populates="category")


class Person(Base):
    """A household member jobs can be tagged with (e.g. you and your
    spouse sharing this app). Purely a filter/label - nobody's data is
    actually restricted by it, so there's no auth tied to this at all."""

    __tablename__ = "people"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    color = Column(String, nullable=False)
    # The resume app's own Person.slug (see that app's app/models.py) that
    # resume generation should tailor for this person's jobs - e.g. "rach".
    # Null means "use the resume app's default person" - so whoever's
    # already the default there needs zero configuration here; only a
    # second household member needs to set this. See app/resume_gen.py.
    resume_person_slug = Column(String, nullable=True)

    jobs = relationship("Job", back_populates="owner")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    company = Column(String, nullable=True)
    company_url = Column(String, nullable=True)
    applied = Column(Boolean, nullable=False, default=False)

    # Who this job belongs to (see Person above). Nullable - jobs imported
    # before this feature existed, or added without picking anyone, are
    # simply unowned rather than defaulted to a guess.
    owner_id = Column(Integer, ForeignKey("people.id"), nullable=True)

    # Populated by bulk CSV import from the job-scoring Chrome extension;
    # null for jobs entered by hand. Re-importing a URL that's already here
    # refreshes these fields only - applied and everything else is left
    # alone, since re-scoring shouldn't touch your tracked progress.
    salary = Column(String, nullable=True)
    tier = Column(String, nullable=True)
    summary = Column(String, nullable=True)
    matched = Column(String, nullable=True)
    gaps = Column(String, nullable=True)
    strengths = Column(String, nullable=True)
    scored_at = Column(DateTime, nullable=True)
    jd_text = Column(String, nullable=True)

    # Populated by the "Generate Resume" feature: a tailored copy of
    # resume data (fetched live from the resume app, then tailored to this
    # job's jd_text by Claude) plus a matching cover letter. Rendered to
    # PDF/DOCX on demand via the resume app, not stored as binary here -
    # see app/resume_gen.py. Regenerating overwrites all three together.
    generated_resume_yaml = Column(String, nullable=True)
    generated_cover_letter = Column(String, nullable=True)
    resume_generated_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="job")
    owner = relationship("Person", back_populates="jobs")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.open)

    # Kept as two distinct columns for a future "due date" feature. For now
    # both are set together whenever a task is placed on the calendar.
    due_date = Column(DateTime, nullable=True)
    scheduled_date = Column(DateTime, nullable=True)

    estimate_minutes = Column(Integer, nullable=True)
    actual_minutes = Column(Integer, nullable=True)

    # Manual priority ordering within a day (or within the backlog). Lower
    # sorts first; left sparse (multiples of 10) so drags can renumber
    # cheaply without touching every row.
    sort_order = Column(Integer, nullable=False, default=0)
    is_important = Column(Boolean, nullable=False, default=False)

    # A task with repeat_daily=True is the origin of a series: on read,
    # missing days from its scheduled_date through repeat_until (or
    # indefinitely) get lazily materialized as independent Task rows
    # carrying series_id back to this one. Each materialized occurrence is
    # otherwise a normal task - done/edits/drags on it never touch siblings.
    repeat_daily = Column(Boolean, nullable=False, default=False)
    repeat_until = Column(DateTime, nullable=True)
    series_id = Column(Integer, ForeignKey("tasks.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Push-notification reminder plan (see app/reminders.py for the
    # scheduler that acts on these). remind_at is the first nag; if
    # remind_snooze_minutes is also set, it keeps re-nagging on that
    # interval until either the task is done or remind_max_count is hit
    # (null = no cap). remind_count_sent/last_reminded_at are bookkeeping
    # the scheduler owns - editing any of the three plan fields above
    # resets both (see crud.update_task), and reopening a done task does
    # too, so a task's nag cycle always restarts clean.
    remind_at = Column(DateTime, nullable=True)
    remind_snooze_minutes = Column(Integer, nullable=True)
    remind_max_count = Column(Integer, nullable=True)
    remind_count_sent = Column(Integer, nullable=False, default=0)
    last_reminded_at = Column(DateTime, nullable=True)

    category = relationship("Category", back_populates="tasks")
    job = relationship("Job", back_populates="tasks")


class PushSubscription(Base):
    """One row per subscribed browser/device (Web Push - see app/push.py).
    Flat list, no owner/person linkage - every subscribed device gets
    every reminder, by explicit choice (this app doesn't have per-task
    ownership the way Job does, and there was no request to add it)."""

    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True)
    endpoint = Column(String, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
