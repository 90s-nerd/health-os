from sqlalchemy import create_engine
from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_config


class Base(DeclarativeBase):
    pass


url = get_config().database_url
engine = create_engine(
    url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {}
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def db_session(request: Request):
    db = SessionLocal()
    profile_id = getattr(request.state, "profile_id", None)
    if profile_id:
        db.info["profile_id"] = profile_id
    try:
        yield db
    finally:
        db.close()
