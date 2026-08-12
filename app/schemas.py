from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from .models import TaskStatus


class CategoryBase(BaseModel):
    name: str
    color: str


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None


class Category(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class JobBase(BaseModel):
    name: str
    url: str
    company: Optional[str] = None
    company_url: Optional[str] = None


class JobCreate(JobBase):
    pass


class JobUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    company: Optional[str] = None
    company_url: Optional[str] = None
    applied: Optional[bool] = None
    salary: Optional[str] = None
    tier: Optional[str] = None
    summary: Optional[str] = None
    matched: Optional[str] = None
    gaps: Optional[str] = None
    strengths: Optional[str] = None
    scored_at: Optional[datetime] = None
    jd_text: Optional[str] = None


class JobSummary(JobBase):
    """Lightweight job shape embedded in Task responses - omits the large
    scoring-detail fields (summary/matched/gaps/strengths/jd_text) so a
    calendar/backlog fetch full of job-linked tasks doesn't balloon in size
    carrying job descriptions nothing on that screen needs. tier is small
    and worth showing on a task card, so it stays.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    applied: bool
    tier: Optional[str] = None
    created_at: datetime


class Job(JobSummary):
    """Full job shape, scoring detail included - used by /api/jobs and the
    job detail modal, where that detail is actually wanted."""

    salary: Optional[str] = None
    summary: Optional[str] = None
    matched: Optional[str] = None
    gaps: Optional[str] = None
    strengths: Optional[str] = None
    scored_at: Optional[datetime] = None
    jd_text: Optional[str] = None

    # generated_resume_yaml is deliberately NOT exposed here - it's large
    # and only ever needed server-side (to render a PDF/DOCX on request).
    # The cover letter is small text the UI displays directly, so it's fine
    # to send as-is; the timestamp is how the UI knows whether a resume
    # exists yet at all (and lets it show "generated 2 days ago").
    generated_cover_letter: Optional[str] = None
    resume_generated_at: Optional[datetime] = None


class JobImportResult(BaseModel):
    created: int
    updated: int
    skipped: int


class ResumeBatchRequest(BaseModel):
    job_ids: List[int]


class ResumeBatchStarted(BaseModel):
    batch_id: str


class ResumeBatchJobResult(BaseModel):
    job_id: int
    name: str
    ok: bool
    error: Optional[str] = None


class ResumeBatchStatus(BaseModel):
    batch_id: str
    total: int
    done: int
    status: str  # "running" | "done"
    results: List[ResumeBatchJobResult]


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    estimate_minutes: Optional[int] = None
    is_important: bool = False
    job_id: Optional[int] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[int] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None
    estimate_minutes: Optional[int] = None
    actual_minutes: Optional[int] = None
    is_important: Optional[bool] = None
    sort_order: Optional[int] = None
    job_id: Optional[int] = None
    repeat_daily: Optional[bool] = None
    repeat_until: Optional[datetime] = None


class Task(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: TaskStatus
    due_date: Optional[datetime] = None
    scheduled_date: Optional[datetime] = None
    actual_minutes: Optional[int] = None
    sort_order: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    job: Optional[JobSummary] = None
    repeat_daily: bool = False
    repeat_until: Optional[datetime] = None
    series_id: Optional[int] = None


class ReorderItem(BaseModel):
    id: int
    scheduled_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    sort_order: int


class ReorderRequest(BaseModel):
    updates: List[ReorderItem]
