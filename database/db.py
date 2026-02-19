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


async def init_db() -> None:
    """
    Создание таблиц в базе данных.
    Вызывать один раз при старте приложения.
    """
    async_engine = get_engine()
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Асинхронный генератор сессий.
    Используется в хендлерах для работы с БД.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        yield session

