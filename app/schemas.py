from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

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


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    estimate_minutes: Optional[int] = None
    is_important: bool = False
    link_url: Optional[str] = None


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
    link_url: Optional[str] = None
    repeat_daily: Optional[bool] = None
    repeat_until: Optional[datetime] = None
    remind_at: Optional[datetime] = None
    remind_snooze_minutes: Optional[int] = None
    remind_max_count: Optional[int] = None


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
    repeat_daily: bool = False
    repeat_until: Optional[datetime] = None
    series_id: Optional[int] = None
    remind_at: Optional[datetime] = None
    remind_snooze_minutes: Optional[int] = None
    remind_max_count: Optional[int] = None
    remind_count_sent: int = 0
    last_reminded_at: Optional[datetime] = None


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    """Matches the browser's PushSubscription.toJSON() shape verbatim, so
    the frontend can POST it straight through with no reshaping."""

    endpoint: str
    keys: PushSubscriptionKeys


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


class ReorderItem(BaseModel):
    id: int
    scheduled_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    sort_order: int


class ReorderRequest(BaseModel):
    updates: List[ReorderItem]


class Me(BaseModel):
    """Who is signed in (GET /api/me). `is_admin` marks an administrator, the only one who can let people in."""

    id: int
    email: str
    is_admin: bool
    logout_url: Optional[str] = None


class UserOut(BaseModel):
    id: int
    email: str
    status: str
    is_admin: bool = False


class UserAdd(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class UserStatus(BaseModel):
    status: Literal["active", "removed"]
