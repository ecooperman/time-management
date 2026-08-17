import csv
import io
import re
import uuid
from datetime import datetime
from typing import List, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import crud, resume_gen, schemas
from ..database import SessionLocal
from ..deps import get_db

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

# In-memory progress tracking for bulk resume generation. Fine for a
# single-process personal app - lost on restart, but that only drops an
# in-flight progress bar, never generated data (each job's row is already
# committed by the time its entry lands here).
_BULK_BATCHES: dict = {}


@router.get("", response_model=List[schemas.Job])
def list_jobs(db: Session = Depends(get_db)):
    return crud.get_jobs(db)


@router.post("/import", response_model=schemas.JobImportResult)
async def import_jobs(
    file: UploadFile = File(...),
    owner_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # -sig strips a BOM if Excel/Sheets added one
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Could not read file as UTF-8 text")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "url" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV is missing a 'url' column")
    return crud.import_jobs_from_csv(db, list(reader), owner_id=owner_id)


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


# --- resume generation ---
# See app/resume_gen.py for the actual fetch-tailor-render flow and
# DEPLOYMENT.md/README.md for the ANTHROPIC_API_KEY / INTERNAL_API_TOKEN
# setup this all depends on.


def _safe_filename(job, ext: str) -> str:
    base = job.name if not job.company else f"{job.name} - {job.company}"
    base = re.sub(r"[^A-Za-z0-9 _.-]", " ", base)  # drop disallowed chars as spaces, not gaps
    base = re.sub(r"\s+", " ", base).strip()
    return f"{base or f'resume_{job.id}'}.{ext}"


def _generate_and_store(db: Session, job) -> None:
    """Fetch+tailor+store for one job; commits on success. Raises
    resume_gen.ResumeGenerationError on failure - nothing is written in
    that case, so a failed attempt never clobbers a previous good result."""
    tailored_yaml, cover_letter = resume_gen.generate_for_job(job)
    job.generated_resume_yaml = tailored_yaml
    job.generated_cover_letter = cover_letter
    job.resume_generated_at = datetime.utcnow()
    db.commit()


@router.post("/{job_id}/generate-resume", response_model=schemas.Job)
def generate_resume(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _generate_and_store(db, job)
    except resume_gen.ResumeGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    db.refresh(job)
    return job


def _download_resume(db: Session, job_id: int, fmt: str) -> Response:
    job = crud.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.generated_resume_yaml:
        raise HTTPException(status_code=404, detail="No resume has been generated for this job yet")
    data = yaml.safe_load(job.generated_resume_yaml)
    try:
        content = resume_gen.render_document(data, fmt)
    except resume_gen.ResumeGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))
    media_type = (
        "application/pdf"
        if fmt == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    filename = _safe_filename(job, fmt)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{job_id}/resume.pdf")
def download_resume_pdf(job_id: int, db: Session = Depends(get_db)):
    return _download_resume(db, job_id, "pdf")


@router.get("/{job_id}/resume.docx")
def download_resume_docx(job_id: int, db: Session = Depends(get_db)):
    return _download_resume(db, job_id, "docx")


def _run_bulk_generation(batch_id: str, job_ids: List[int]) -> None:
    """Runs in the background after generate_resumes_bulk's response is
    already sent - opens its own DB session rather than reusing the
    request's, since this can run for a while (one Claude call + one
    resume-app fetch per job, sequentially) well past when the request's
    session would normally be torn down."""
    batch = _BULK_BATCHES[batch_id]
    db = SessionLocal()
    try:
        for job_id in job_ids:
            job = crud.get_job(db, job_id)
            result = {
                "job_id": job_id,
                "name": job.name if job is not None else f"Job #{job_id}",
                "ok": False,
                "error": None,
            }
            if job is None:
                result["error"] = "Job no longer exists"
            else:
                try:
                    _generate_and_store(db, job)
                    result["ok"] = True
                except resume_gen.ResumeGenerationError as e:
                    result["error"] = str(e)
            batch["results"].append(result)
            batch["done"] += 1
    finally:
        db.close()
        batch["status"] = "done"


@router.post("/generate-resumes-bulk", response_model=schemas.ResumeBatchStarted)
def generate_resumes_bulk(
    body: schemas.ResumeBatchRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    jobs = crud.get_jobs_by_ids(db, body.job_ids)
    if not jobs:
        raise HTTPException(status_code=400, detail="No matching jobs found")

    batch_id = uuid.uuid4().hex
    _BULK_BATCHES[batch_id] = {"total": len(jobs), "done": 0, "status": "running", "results": []}
    background_tasks.add_task(_run_bulk_generation, batch_id, [j.id for j in jobs])
    return schemas.ResumeBatchStarted(batch_id=batch_id)


@router.get("/generate-resumes-bulk/{batch_id}", response_model=schemas.ResumeBatchStatus)
def get_bulk_status(batch_id: str):
    batch = _BULK_BATCHES.get(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return schemas.ResumeBatchStatus(batch_id=batch_id, **batch)
