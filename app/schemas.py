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


class Job(JobBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    applied: bool
    created_at: datetime


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
    job: Optional[Job] = None
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
