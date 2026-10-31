"""Separate database connection and session management for growth_demo.db."""
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_FILE = PROJECT_ROOT / "growth_demo.db"
GROWTH_DATABASE_URL = f"sqlite:///{DB_FILE}"

growth_engine = create_engine(
    GROWTH_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

GrowthSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=growth_engine)


def get_growth_db():
    """Dependency for growth demo database session."""
    db = GrowthSessionLocal()
    try:
        yield db
    finally:
        db.close()

