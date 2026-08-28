from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("", response_model=List[schemas.Task])
def list_tasks(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    return crud.get_tasks(db, start, end)


@router.get("/backlog", response_model=List[schemas.Task])
def list_backlog(db: Session = Depends(get_db)):
    return crud.get_backlog(db)


@router.post("", response_model=schemas.Task)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    return crud.create_task(db, task)


@router.get("/{task_id}", response_model=schemas.Task)
def get_task(task_id: int, db: Session = Depends(get_db)):
    # Registered after the "/backlog" literal route above on purpose - a
    # "/{task_id}" pattern registered first would shadow it (task_id=
    # "backlog" fails int coercion before ever reaching list_backlog).
    task = crud.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/reorder", response_model=List[schemas.Task])
def reorder_tasks(payload: schemas.ReorderRequest, db: Session = Depends(get_db)):
    return crud.reorder_tasks(db, payload.updates)


@router.patch("/{task_id}", response_model=schemas.Task)
def update_task(task_id: int, updates: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = crud.update_task(db, task_id, updates)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("/{task_id}/stop-recurrence", response_model=schemas.Task)
def stop_recurrence(task_id: int, db: Session = Depends(get_db)):
    """Ends the recurring series task_id belongs to (origin or occurrence,
    either works) as of task_id's own date - see crud.stop_recurrence."""
    origin = crud.stop_recurrence(db, task_id)
    if origin is None:
        raise HTTPException(status_code=404, detail="Task not found, or isn't part of a recurring series")
    return origin


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    ok = crud.delete_task(db, task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}
