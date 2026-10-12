import os

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL") or URL.create(
    "postgresql+psycopg",
    username=os.getenv("POSTGRES_USER", "finance"),
    password=os.getenv("POSTGRES_PASSWORD", "finance_password"),
    host="db", port=5432,
    database=os.getenv("POSTGRES_DB", "finance_db"),
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()