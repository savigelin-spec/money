"""
Запросы и утилиты для работы с базой данных.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import APPLICATION_COST, TRANSACTION_WITHDRAWAL, TRANSACTION_DEPOSIT
from .models import (
    User,
    Application,
    ModerationSession,
    Transaction,
    ModeratorStats,
    ModeratorNotification,
)


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    """Получить пользователя или создать нового."""
    result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
        await session.flush()

    return user


async def change_balance(
    session: AsyncSession,
    user: User,
    amount: int,
    description: str,
    is_deposit: bool,
) -> User:
    """Изменить баланс пользователя и записать транзакцию (в звёздах)."""
    user.balance += amount

    transaction = Transaction(
        user_id=user.user_id,
        amount=amount,
        type=TRANSACTION_DEPOSIT if is_deposit else TRANSACTION_WITHDRAWAL,
        description=description,
    )
    session.add(transaction)

    await session.flush()
    return user


async def can_create_application(session: AsyncSession, user: User) -> bool:
    """Проверка, может ли пользователь создать новую заявку (есть баланс и нет активной)."""
    if user.balance < APPLICATION_COST:
        return False

    result = await session.execute(
        select(Application).where(
            Application.user_id == user.user_id,
            Application.status.in_(["pending", "moderating"]),
        )
    )
    existing = result.scalar_one_or_none()
    return existing is None


async def create_application(
    session: AsyncSession,
    user: User,
    queue_position: int | None = None,
    estimated_wait_time: int | None = None,
) -> Application:
    """Создать заявку и сразу списать средства."""
    # Списание средств
    await change_balance(
        session=session,
        user=user,
        amount=-APPLICATION_COST,
        description="Списание за заявку на подтверждение возраста",
        is_deposit=False,
    )

    application = Application(
        user_id=user.user_id,
        status="pending",
        queue_position=queue_position,
        estimated_wait_time=estimated_wait_time,
    )
    session.add(application)
    await session.flush()
    return application


async def cancel_application(
    session: AsyncSession,
    application: Application,
    user: User,
) -> None:
    """Отменить заявку и вернуть средства пользователю."""
    if application.status != "pending":
        raise ValueError("Можно отменить только заявки в статусе pending")
    
    if application.user_id != user.user_id:
        raise ValueError("Пользователь может отменить только свою заявку")
    
    # Возвращаем средства
    await change_balance(
        session=session,
        user=user,
        amount=APPLICATION_COST,
        description=f"Возврат средств за отмену заявки #{application.id}",
        is_deposit=True,
    )
    
    # Изменяем статус заявки на cancelled
    application.status = "cancelled"
    await session.flush()
    
    # Обновляем позиции в очереди после отмены
    # Импортируем здесь, чтобы избежать циклического импорта
    from utils.queue import update_queue_positions
    await update_queue_positions(session)


async def get_pending_applications(session: AsyncSession) -> Sequence[Application]:
    """Получить список ожидающих заявок (pending), отсортированных по позиции в очереди и дате."""
    result = await session.execute(
        select(Application)
        .where(Application.status == "pending")
        .order_by(
            Application.queue_position.is_(None),
            Application.queue_position,
            Application.created_at,
        )
    )
    return result.scalars().all()


async def assign_moderator_to_application(
    session: AsyncSession,
    application: Application,
    moderator_id: int,
) -> Application:
    """Назначить модератора на заявку и обновить статус/время старта."""
    application.moderator_id = moderator_id
    application.status = "moderating"
    application.started_at = datetime.utcnow()

    await session.flush()
    return application


async def create_moderation_session(
    session: AsyncSession,
    application: Application,
) -> ModerationSession:
    """Создать сессию модерации для заявки."""
    if application.moderator_id is None:
        raise ValueError("У заявки нет назначенного модератора")

    moderation_session = ModerationSession(
        application_id=application.id,
        user_id=application.user_id,
        moderator_id=application.moderator_id,
        status="active",
    )
    session.add(moderation_session)
    await session.flush()
    return moderation_session


async def set_session_user_photo(
    session: AsyncSession,
    moderation_session: ModerationSession,
    file_id: str,
) -> None:
    """Сохранить file_id скриншота пользователя в сессии."""
    moderation_session.user_photo_file_id = file_id
    await session.flush()


async def set_session_moderator_photo(
    session: AsyncSession,
    moderation_session: ModerationSession,
    file_id: str,
) -> None:
    """Сохранить file_id фото модератора в сессии."""
    moderation_session.moderator_photo_file_id = file_id
    await session.flush()


async def complete_moderation_session(
    session: AsyncSession,
    moderation_session: ModerationSession,
    application_status: str,
) -> None:
    """Завершить сессию модерации и обновить заявку."""
    moderation_session.status = "completed"

    # Получаем заявку напрямую через запрос, чтобы избежать проблем с lazy loading
    application = await get_application_by_id(session, moderation_session.application_id)
    if application:
        application.status = application_status
        application.completed_at = datetime.utcnow()

    await session.flush()


async def get_or_create_moderator_stats(
    session: AsyncSession,
    moderator_id: int,
) -> ModeratorStats:
    """Получить или создать статистику модератора."""
    result = await session.execute(
        select(ModeratorStats).where(ModeratorStats.moderator_id == moderator_id)
    )
    stats = result.scalar_one_or_none()

    if stats is None:
        stats = ModeratorStats(
            moderator_id=moderator_id,
            total_sessions=0,
            total_time_seconds=0,
            average_session_time=0.0,
        )
        session.add(stats)
        await session.flush()

    return stats


async def update_moderator_stats_after_session(
    session: AsyncSession,
    moderator_id: int,
    session_duration_seconds: int,
) -> ModeratorStats:
    """Обновить статистику модератора после завершения сессии."""
    stats = await get_or_create_moderator_stats(session, moderator_id)

    stats.total_sessions += 1
    stats.total_time_seconds += session_duration_seconds
    if stats.total_sessions > 0:
        stats.average_session_time = stats.total_time_seconds / stats.total_sessions

    await session.flush()
    return stats


async def get_average_session_time_global(
    session: AsyncSession,
    default_value: int,
) -> float:
    """
    Получить среднее время сессии по всем модераторам.
    Если статистики нет — вернуть default_value.
    """
    result = await session.execute(
        select(func.avg(ModeratorStats.average_session_time))
    )
    value = result.scalar_one_or_none()
    return float(value) if value is not None else float(default_value)


async def get_user_applications(
    session: AsyncSession,
    user_id: int,
) -> Sequence[Application]:
    """Получить все заявки пользователя, отсортированные по дате создания."""
    result = await session.execute(
        select(Application)
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
    )
    return result.scalars().all()


async def get_application_by_id(
    session: AsyncSession,
    application_id: int,
) -> Application | None:
    """Получить заявку по ID."""
    result = await session.execute(
        select(Application).where(Application.id == application_id)
    )
    return result.scalar_one_or_none()


async def get_active_moderation_sessions_by_moderator(
    session: AsyncSession,
    moderator_id: int,
) -> Sequence[ModerationSession]:
    """Получить активные сессии модератора."""
    result = await session.execute(
        select(ModerationSession)
        .where(
            ModerationSession.moderator_id == moderator_id,
            ModerationSession.status == "active"
        )
        .order_by(ModerationSession.created_at.desc())
    )
    return result.scalars().all()


async def get_completed_moderation_sessions_by_moderator(
    session: AsyncSession,
    moderator_id: int,
    limit: int = 10,
) -> Sequence[ModerationSession]:
    """Получить завершенные сессии модератора (для отправки фото после подтверждения)."""
    result = await session.execute(
        select(ModerationSession)
        .where(
            ModerationSession.moderator_id == moderator_id,
            ModerationSession.status == "completed",
            ModerationSession.moderator_photo_file_id.is_(None)  # Только без фото
        )
        .order_by(ModerationSession.created_at.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_moderation_session_by_id(
    session: AsyncSession,
    session_id: int,
) -> ModerationSession | None:
    """Получить сессию модерации по ID."""
    result = await session.execute(
        select(ModerationSession).where(ModerationSession.id == session_id)
    )
    return result.scalar_one_or_none()


async def get_active_moderation_session_by_user(
    session: AsyncSession,
    user_id: int,
) -> ModerationSession | None:
    """Получить активную сессию модерации пользователя."""
    result = await session.execute(
        select(ModerationSession)
        .where(
            ModerationSession.user_id == user_id,
            ModerationSession.status == "active"
        )
    )
    return result.scalar_one_or_none()


async def set_user_main_message_id(
    session: AsyncSession,
    user_id: int,
    message_id: int,
) -> None:
    """Сохранить ID главного сообщения пользователя."""
    user = await get_or_create_user(session, user_id=user_id)
    user.main_message_id = message_id
    await session.flush()


async def set_moderator_photo_message_id(
    session: AsyncSession,
    session_id: int,
    message_id: int,
) -> None:
    """Сохранить ID сообщения с фото от модератора."""
    from database.models import ModerationSession
    result = await session.execute(
        select(ModerationSession).where(ModerationSession.id == session_id)
    )
    moderation_session = result.scalar_one_or_none()
    if moderation_session:
        moderation_session.moderator_photo_message_id = message_id
        await session.flush()


async def set_moderator_screenshot_message_id(
    session: AsyncSession,
    session_id: int,
    message_id: int,
) -> None:
    """Сохранить ID сообщения «Скриншот от пользователя» в чате модератора."""
    result = await session.execute(
        select(ModerationSession).where(ModerationSession.id == session_id)
    )
    moderation_session = result.scalar_one_or_none()
    if moderation_session:
        moderation_session.moderator_screenshot_message_id = message_id
        await session.flush()


async def set_moderator_own_photo_message_id(
    session: AsyncSession,
    session_id: int,
    message_id: int,
) -> None:
    """Сохранить ID сообщения модератора с фото в его чате."""
    result = await session.execute(
        select(ModerationSession).where(ModerationSession.id == session_id)
    )
    moderation_session = result.scalar_one_or_none()
    if moderation_session:
        moderation_session.moderator_own_photo_message_id = message_id
        await session.flush()


async def get_moderation_session_by_application_id(
    session: AsyncSession,
    application_id: int,
) -> ModerationSession | None:
    """Получить сессию модерации по ID заявки (одна сессия на заявку)."""
    result = await session.execute(
        select(ModerationSession).where(
            ModerationSession.application_id == application_id
        )
    )
    return result.scalar_one_or_none()


async def set_user_info_message_id(
    session: AsyncSession,
    session_id: int,
    message_id: int,
) -> None:
    """Сохранить ID информационного сообщения пользователя в сессии."""
    moderation_session = await get_moderation_session_by_id(session, session_id)
    if moderation_session:
        moderation_session.user_info_message_id = message_id
        await session.flush()


async def set_user_invoice_message_id(
    session: AsyncSession,
    user_id: int,
    message_id: int,
) -> None:
    """Сохранить ID сообщения с инвойсом пользователя."""
    user = await get_or_create_user(session, user_id=user_id)
    user.invoice_message_id = message_id
    await session.flush()


async def get_user_invoice_message_id(
    session: AsyncSession,
    user_id: int,
) -> int | None:
    """Получить ID сообщения с инвойсом пользователя."""
    user = await get_or_create_user(session, user_id=user_id)
    return user.invoice_message_id


async def get_user_message_ids(
    session: AsyncSession,
    user_id: int,
) -> tuple[int | None, int | None]:
    """
    Получить ID главного и информационного сообщений пользователя.
    Возвращает (main_message_id, info_message_id).
    """
    user = await get_or_create_user(session, user_id=user_id)
    main_message_id = user.main_message_id

    # Получаем активную сессию для info_message_id
    moderation_session = await get_active_moderation_session_by_user(session, user_id)
    info_message_id = moderation_session.user_info_message_id if moderation_session else None

    return (main_message_id, info_message_id)


async def get_all_moderators(session: AsyncSession) -> Sequence[User]:
    """Получить всех модераторов и админов."""
    from config import ROLE_MODERATOR, ROLE_ADMIN
    
    result = await session.execute(
        select(User).where(
            User.role.in_([ROLE_MODERATOR, ROLE_ADMIN])
        )
    )
    return result.scalars().all()


async def save_moderator_notification(
    session: AsyncSession,
    moderator_id: int,
    application_id: int,
    message_id: int,
) -> ModeratorNotification:
    """Сохранить уведомление модератора о новой заявке."""
    notification = ModeratorNotification(
        moderator_id=moderator_id,
        application_id=application_id,
        message_id=message_id,
    )
    session.add(notification)
    await session.flush()
    return notification


async def get_moderator_notifications_for_application(
    session: AsyncSession,
    application_id: int,
) -> list[ModeratorNotification]:
    """Получить все уведомления для заявки."""
    result = await session.execute(
        select(ModeratorNotification).where(
            ModeratorNotification.application_id == application_id
        )
    )
    return list(result.scalars().all())


async def delete_moderator_notification(
    session: AsyncSession,
    notification_id: int,
) -> None:
    """Удалить уведомление из БД."""
    result = await session.execute(
        select(ModeratorNotification).where(
            ModeratorNotification.id == notification_id
        )
    )
    notification = result.scalar_one_or_none()
    if notification:
        await session.delete(notification)
        await session.flush()

