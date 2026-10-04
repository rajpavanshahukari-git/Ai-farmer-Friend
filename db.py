"""SQLAlchemy engine/session. Works with SQLite (dev) and PostgreSQL (set DATABASE_URL)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config.settings import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import models  # noqa: F401  (register tables)
    from app.database.seed import seed_demo_farmer

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo_farmer(db)
