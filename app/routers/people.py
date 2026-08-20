from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import crud, resume_gen, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/people", tags=["people"])


@router.get("", response_model=List[schemas.Person])
def list_people(db: Session = Depends(get_db)):
    return crud.get_people(db)


@router.get("/resume-people")
def list_resume_people():
    """Proxies the resume app's own list of people - source for the
    "Resume" dropdown on each person's row in Settings. The browser never
    talks to the resume app directly (same boundary as actual resume
    generation) - this just passes the list through."""
    try:
        return {"people": resume_gen.list_resume_people()}
    except resume_gen.ResumeGenerationError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("", response_model=schemas.Person)
def create_person(person: schemas.PersonCreate, db: Session = Depends(get_db)):
    return crud.create_person(db, person)


@router.patch("/{person_id}", response_model=schemas.Person)
def update_person(person_id: int, updates: schemas.PersonUpdate, db: Session = Depends(get_db)):
    person = crud.update_person(db, person_id, updates)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.delete("/{person_id}")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    result = crud.delete_person(db, person_id)
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Person not found")
    if result == "in_use":
        raise HTTPException(status_code=409, detail="Person still has jobs assigned to them")
    return {"ok": True}
