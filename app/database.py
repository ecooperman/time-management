import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# DATABASE_URL lets the tests (and migrations, see migrations/env.py) - or a
# scratch copy for trying something out - use another database; the default is
# the app's own file.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./tasks.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
