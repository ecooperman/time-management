from sqlalchemy.orm import Session

from . import models

DEFAULT_CATEGORIES = [
    {"name": "Home", "color": "#4C9F70"},
    {"name": "Resume-Building", "color": "#4C7CAF"},
    {"name": "Applying for Jobs", "color": "#C97B4A"},
]


def seed_categories(db: Session) -> None:
    if db.query(models.Category).count() == 0:
        for cat in DEFAULT_CATEGORIES:
            db.add(models.Category(**cat))
        db.commit()
