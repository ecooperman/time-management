from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=List[schemas.Job])
def list_jobs(db: Session = Depends(get_db)):
    return crud.get_jobs(db)


@router.post("", response_model=schemas.Job)
def create_job(job: schemas.JobCreate, db: Session = Depends(get_db)):
    return crud.create_job(db, job)


@router.patch("/{job_id}", response_model=schemas.Job)
def update_job(job_id: int, updates: schemas.JobUpdate, db: Session = Depends(get_db)):
    job = crud.update_job(db, job_id, updates)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    result = crud.delete_job(db, job_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Job not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Job still has tasks linked to it")
    return {"ok": True}
