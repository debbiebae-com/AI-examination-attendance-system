from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATA_DIR, DATABASE_URL

DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite needs check_same_thread=False for use across FastAPI threads; other databases
# (e.g. Supabase Postgres) reject that argument. pool_pre_ping keeps hosted connections
# healthy by transparently reconnecting dropped ones.
_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session():
    """FastAPI dependency that yields a database session per request."""
    with SessionLocal() as session:
        yield session
