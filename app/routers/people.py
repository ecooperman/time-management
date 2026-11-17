from typing import List

from fastapi import APIRouter, Depends, HTTPException
from shared_python import accounts_gate
from shared_python.accounts_gate import Account
from sqlalchemy.orm import Session

from .. import crud, resume_gen, schemas
from ..deps import get_db

router = APIRouter(prefix="/api/people", tags=["people"])


@router.get("", response_model=List[schemas.Person])
def list_people(db: Session = Depends(get_db)):
    return crud.get_people(db)


def _only_an_administrator_may_pick_a_resume(account: Account, fields: dict) -> None:
    """Which resume a person's jobs are tailored from names a person in the ADMINISTRATOR's resume app, so an
    ordinary account cannot set it (resume generation is the administrator's alone)."""
    if fields.get("resume_person_slug") is not None and not account.is_admin:
        raise HTTPException(status_code=403, detail="Only an administrator can choose a resume")


@router.get("/resume-people", dependencies=[Depends(accounts_gate.require_admin)])
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
def create_person(
    person: schemas.PersonCreate, db: Session = Depends(get_db), account: Account = Depends(accounts_gate.current_account)
):
    _only_an_administrator_may_pick_a_resume(account, person.model_dump())
    return crud.create_person(db, person)


@router.patch("/{person_id}", response_model=schemas.Person)
def update_person(
    person_id: int,
    updates: schemas.PersonUpdate,
    db: Session = Depends(get_db),
    account: Account = Depends(accounts_gate.current_account),
):
    _only_an_administrator_may_pick_a_resume(account, updates.model_dump(exclude_unset=True))
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
