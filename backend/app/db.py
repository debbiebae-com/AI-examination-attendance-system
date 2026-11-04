from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """FastAPI dependency that yields a database session per request."""
    with SessionLocal() as session:
        yield session
