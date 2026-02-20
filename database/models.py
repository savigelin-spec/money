"""
SQLAlchemy модели для базы данных.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    String,
    Integer,
    Float,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Базовый класс моделей."""


class User(Base):
    """Пользователь бота."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)  # Telegram user_id
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))

    balance: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[str] = mapped_column(String(32), default="user")

    main_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoice_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # отношения
    applications: Mapped[list["Application"]] = relationship(
        back_populates="user",
        foreign_keys="Application.user_id",
        cascade="all, delete-orphan"
    )
    moderation_sessions_as_user: Mapped[list["ModerationSession"]] = relationship(
        back_populates="user",
        foreign_keys="ModerationSession.user_id",
    )
    moderation_sessions_as_moderator: Mapped[list["ModerationSession"]] = relationship(
        back_populates="moderator",
        foreign_keys="ModerationSession.moderator_id",
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    moderator_stats: Mapped["ModeratorStats | None"] = relationship(
        back_populates="moderator",
        foreign_keys="ModeratorStats.moderator_id",
        uselist=False
    )


class Application(Base):
    """Заявка на подтверждение возраста."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    queue_position: Mapped[int | None] = mapped_column(Integer)
    estimated_wait_time: Mapped[int | None] = mapped_column(Integer)  # секунды

    moderator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # отношения
    user: Mapped["User"] = relationship(back_populates="applications", foreign_keys=[user_id])
    moderator: Mapped["User | None"] = relationship(
        foreign_keys=[moderator_id],
        viewonly=True,
    )
    moderation_session: Mapped["ModerationSession | None"] = relationship(
        back_populates="application", uselist=False
    )


class ModerationSession(Base):
    """Сессия модерации (общение пользователя с модератором)."""

    __tablename__ = "moderation_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    moderator_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )

    user_photo_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderator_photo_file_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_main_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_info_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moderator_photo_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moderator_screenshot_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moderator_own_photo_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(32), default="active")

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # отношения
    application: Mapped["Application"] = relationship(
        back_populates="moderation_session"
    )
    user: Mapped["User"] = relationship(
        back_populates="moderation_sessions_as_user",
        foreign_keys=[user_id],
    )
    moderator: Mapped["User"] = relationship(
        back_populates="moderation_sessions_as_moderator",
        foreign_keys=[moderator_id],
    )


class Transaction(Base):
    """Транзакция по балансу пользователя."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # отношения
    user: Mapped["User"] = relationship(back_populates="transactions")


class ModeratorStats(Base):
    """Статистика модератора для расчёта среднего времени сессии."""

    __tablename__ = "moderator_stats"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    moderator_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"), nullable=False, unique=True
    )
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    total_time_seconds: Mapped[int] = mapped_column(Integer, default=0)
    average_session_time: Mapped[float] = mapped_column(Float, default=0.0)

    # отношения
    moderator: Mapped["User"] = relationship(back_populates="moderator_stats")

    __table_args__ = (
        UniqueConstraint("moderator_id", name="uq_moderator_stats_moderator_id"),
    )


class ModeratorNotification(Base):
    """Уведомление модератора о новой заявке."""

    __tablename__ = "moderator_notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    moderator_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"), nullable=False
    )
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"), nullable=False
    )
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow
    )

    # Индексы для быстрого поиска
    __table_args__ = (
        Index('ix_moderator_notifications_application_id', 'application_id'),
        Index('ix_moderator_notifications_moderator_id', 'moderator_id'),
    )

