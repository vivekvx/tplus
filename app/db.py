"""SQLite + SQLAlchemy setup. ponytail: SQLite for demo; swap URL for Postgres if scale needs it."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///tplus.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def init_db():
    Base.metadata.create_all(engine)
