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
        # timeout: при одновременном доступе вторая сессия ждёт вместо "database is locked"
        engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            future=True,
            connect_args={"timeout": 30},
        )
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


def _ensure_last_user_activity_at_column(conn) -> None:
    """Добавить колонку last_user_activity_at в moderation_sessions для лайв-чата."""
    from sqlalchemy import text
    rows = conn.execute(text("PRAGMA table_info(moderation_sessions)")).fetchall()
    if not any(r[1] == "last_user_activity_at" for r in rows):
        conn.execute(text("ALTER TABLE moderation_sessions ADD COLUMN last_user_activity_at DATETIME"))


def _ensure_moderation_session_messages_table(conn) -> None:
    """Создать таблицу moderation_session_messages для лайв-чата."""
    from sqlalchemy import text
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS moderation_session_messages (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES moderation_sessions(id) ON DELETE CASCADE,
            chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))


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
        await conn.run_sync(_ensure_last_user_activity_at_column)
        await conn.run_sync(_ensure_moderation_session_messages_table)


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Асинхронный генератор сессий.
    Используется в хендлерах для работы с БД.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        yield session

