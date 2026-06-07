"""Database setup for the WildIdea web app."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from . import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_user_consent_columns()
    _ensure_user_email_verification_column()
    _ensure_candidate_reroll_column()
    _ensure_candidate_advantage_column()


def _ensure_user_consent_columns() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    statements: list[str] = []
    if "improvement_consent" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN improvement_consent BOOLEAN NOT NULL DEFAULT 0")
    if "improvement_consent_at" not in columns:
        statements.append("ALTER TABLE users ADD COLUMN improvement_consent_at DATETIME")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_candidate_reroll_column() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("candidates")}
    if "reroll_count" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE candidates ADD COLUMN reroll_count INTEGER NOT NULL DEFAULT 0"))


def _ensure_candidate_advantage_column() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("candidates")}
    if "advantage" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE candidates ADD COLUMN advantage TEXT NOT NULL DEFAULT ''"))


def _ensure_user_email_verification_column() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("users")}
    if "email_verified_at" in columns:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN email_verified_at DATETIME"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
