"""Create database connections and provide request-scoped sessions."""

from functools import lru_cache
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import get_settings

@lru_cache
def get_engine():
    return create_engine(get_settings().DATABASE_URL, pool_pre_ping=True)

def get_db():
    """Open a database session for one API request and close it afterward."""
    with sessionmaker(bind=get_engine())() as db:
        yield db
