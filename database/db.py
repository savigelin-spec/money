"""
Инициализация и настройка базы данных (SQLite + SQLAlchemy async).
"""
from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import DATABASE_PATH
from .models import Base


DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"


engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Ленивое создание движка БД."""
    global engine
    if engine is None:
        engine = create_async_engine(DATABASE_URL, echo=False, future=True)
    return engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Ленивое создание фабрики сессий."""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return SessionLocal


def _ensure_main_message_id_column(conn) -> None:
    """Добавить колонку main_message_id в users, если её нет (миграция для старых БД)."""
    from sqlalchemy import text
    rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
    # rows: (cid, name, type, notnull, default, pk)
    if not any(r[1] == "main_message_id" for r in rows):
        conn.execute(text("ALTER TABLE users ADD COLUMN main_message_id INTEGER"))


def _ensure_invoice_message_id_column(conn) -> None:
    """Добавить колонку invoice_message_id в users, если её нет (миграция для старых БД)."""
    from sqlalchemy import text
    rows = conn.execute(text("PRAGMA table_info(users)")).fetchall()
    # rows: (cid, name, type, notnull, default, pk)
    if not any(r[1] == "invoice_message_id" for r in rows):
        conn.execute(text("ALTER TABLE users ADD COLUMN invoice_message_id INTEGER"))


def _ensure_moderator_photo_message_id_column(conn) -> None:
    """Добавить колонку moderator_photo_message_id в moderation_sessions, если её нет (миграция для старых БД)."""
    from sqlalchemy import text
    rows = conn.execute(text("PRAGMA table_info(moderation_sessions)")).fetchall()
    # rows: (cid, name, type, notnull, default, pk)
    if not any(r[1] == "moderator_photo_message_id" for r in rows):
        conn.execute(text("ALTER TABLE moderation_sessions ADD COLUMN moderator_photo_message_id INTEGER"))


def _ensure_moderator_screenshot_message_id_column(conn) -> None:
    """Добавить колонку moderator_screenshot_message_id в moderation_sessions, если её нет (миграция для старых БД)."""
    from sqlalchemy import text
    rows = conn.execute(text("PRAGMA table_info(moderation_sessions)")).fetchall()
    if not any(r[1] == "moderator_screenshot_message_id" for r in rows):
        conn.execute(text("ALTER TABLE moderation_sessions ADD COLUMN moderator_screenshot_message_id INTEGER"))


def _ensure_moderator_own_photo_message_id_column(conn) -> None:
    """Добавить колонку moderator_own_photo_message_id в moderation_sessions, если её нет (миграция для старых БД)."""
    from sqlalchemy import text
    rows = conn.execute(text("PRAGMA table_info(moderation_sessions)")).fetchall()
    if not any(r[1] == "moderator_own_photo_message_id" for r in rows):
        conn.execute(text("ALTER TABLE moderation_sessions ADD COLUMN moderator_own_photo_message_id INTEGER"))


async def init_db() -> None:
    """
    Создание таблиц в базе данных.
    Вызывать один раз при старте приложения.
    """
    async_engine = get_engine()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_ensure_main_message_id_column)
        await conn.run_sync(_ensure_invoice_message_id_column)
        await conn.run_sync(_ensure_moderator_photo_message_id_column)
        await conn.run_sync(_ensure_moderator_screenshot_message_id_column)
        await conn.run_sync(_ensure_moderator_own_photo_message_id_column)


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Асинхронный генератор сессий.
    Используется в хендлерах для работы с БД.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        yield session

