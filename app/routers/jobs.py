import csv
import io
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import crud, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("", response_model=List[schemas.Job])
def list_jobs(db: Session = Depends(get_db)):
    return crud.get_jobs(db)


@router.post("/import", response_model=schemas.JobImportResult)
async def import_jobs(file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # -sig strips a BOM if Excel/Sheets added one
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not read file as UTF-8 text")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "url" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is missing a 'url' column")
    return crud.import_jobs_from_csv(db, list(reader))


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
