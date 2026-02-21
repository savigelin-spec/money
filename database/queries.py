"""
Запросы и утилиты для работы с базой данных.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, select, update, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    APPLICATION_COST,
    TRANSACTION_WITHDRAWAL,
    TRANSACTION_DEPOSIT,
    STATUS_COMPLETED,
    STATUS_REJECTED,
    STATUS_PENDING,
    STATUS_MODERATING,
)
from .models import (
    User,
    Application,
    ModerationSession,
    ModerationSessionMessage,
    Transaction,
    ModeratorStats,
    ModeratorNotification,
    TrafficSourceCost,
    TrafficChannel,
    TrafficChannelSource,
)
from utils.traffic import extract_channel_from_source


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

    now = datetime.utcnow()
    moderation_session = ModerationSession(
        application_id=application.id,
        user_id=application.user_id,
        moderator_id=application.moderator_id,
        status="active",
        last_user_activity_at=now,
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


async def end_session_chat_only(
    session: AsyncSession,
    moderation_session: ModerationSession,
) -> None:
    """Завершить только чат сессии (без смены статуса заявки). Заявка остаётся moderating."""
    moderation_session.status = "completed"
    await session.flush()


async def add_session_message(
    session: AsyncSession,
    session_id: int,
    chat_id: int,
    message_id: int,
) -> None:
    """Добавить message_id сообщения бота в лайв-чате для последующего удаления."""
    row = ModerationSessionMessage(
        session_id=session_id,
        chat_id=chat_id,
        message_id=message_id,
    )
    session.add(row)
    await session.flush()


async def get_session_message_ids(
    session: AsyncSession,
    session_id: int,
) -> list[tuple[int, int]]:
    """Получить список (chat_id, message_id) сообщений лайв-чата сессии."""
    result = await session.execute(
        select(ModerationSessionMessage.chat_id, ModerationSessionMessage.message_id).where(
            ModerationSessionMessage.session_id == session_id
        )
    )
    return list(result.all())


async def delete_session_message_rows(
    session: AsyncSession,
    session_id: int,
) -> None:
    """Удалить все записи moderation_session_messages для сессии."""
    await session.execute(delete(ModerationSessionMessage).where(
        ModerationSessionMessage.session_id == session_id
    ))
    await session.flush()


async def update_last_user_activity(
    session: AsyncSession,
    moderation_session: ModerationSession,
) -> None:
    """Обновить время последней активности пользователя в сессии."""
    moderation_session.last_user_activity_at = datetime.utcnow()
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


async def get_user_queue_count(session: AsyncSession, user_id: int) -> int:
    """Количество заявок пользователя в очереди (pending или moderating)."""
    q = (
        select(func.count(Application.id))
        .where(Application.user_id == user_id)
        .where(Application.status.in_([STATUS_PENDING, STATUS_MODERATING]))
    )
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_user_completed_count(
    session: AsyncSession,
    user_id: int,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Количество успешно завершённых заявок пользователя за период (по completed_at)."""
    q = (
        select(func.count(Application.id))
        .where(Application.user_id == user_id)
        .where(Application.status == STATUS_COMPLETED)
        .where(Application.completed_at.isnot(None))
    )
    if start_date is not None:
        q = q.where(Application.completed_at >= start_date)
    if end_date is not None:
        q = q.where(Application.completed_at <= end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


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


# --- Статистика (для utils.statistics и utils.marketing) ---

def _transaction_date_filter(q, start_date: datetime | None, end_date: datetime | None):
    """Применить фильтр по дате к запросу транзакций."""
    if start_date is not None:
        q = q.where(Transaction.created_at >= start_date)
    if end_date is not None:
        q = q.where(Transaction.created_at <= end_date)
    return q


def _application_date_filter(q, start_date: datetime | None, end_date: datetime | None):
    """Применить фильтр по дате к запросу заявок."""
    if start_date is not None:
        q = q.where(Application.created_at >= start_date)
    if end_date is not None:
        q = q.where(Application.created_at <= end_date)
    return q


def _user_date_filter(q, start_date: datetime | None, end_date: datetime | None):
    """Применить фильтр по дате к запросу пользователей."""
    if start_date is not None:
        q = q.where(User.created_at >= start_date)
    if end_date is not None:
        q = q.where(User.created_at <= end_date)
    return q


async def get_total_revenue(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Сумма поступлений (депозиты) за период."""
    q = select(func.coalesce(func.sum(Transaction.amount), 0)).where(
        Transaction.type == TRANSACTION_DEPOSIT
    )
    q = _transaction_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_paying_users(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Количество уникальных пользователей с хотя бы одним депозитом за период."""
    q = select(func.count(func.distinct(Transaction.user_id))).where(
        Transaction.type == TRANSACTION_DEPOSIT
    )
    q = _transaction_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_total_deposits(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Количество депозитов за период (число транзакций)."""
    q = select(func.count(Transaction.id)).where(
        Transaction.type == TRANSACTION_DEPOSIT
    )
    q = _transaction_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_total_withdrawals(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Сумма списаний (по модулю) за период."""
    q = select(func.coalesce(func.sum(func.abs(Transaction.amount)), 0)).where(
        Transaction.type == TRANSACTION_WITHDRAWAL
    )
    q = _transaction_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_net_revenue(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Чистая выручка: депозиты минус списания."""
    total_d = await get_total_revenue(session, start_date, end_date)
    total_w = await get_total_withdrawals(session, start_date, end_date)
    return total_d - total_w


async def get_total_applications(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Общее количество заявок за период."""
    q = select(func.count(Application.id))
    q = _application_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_applications_by_status(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, int]:
    """Количество заявок по статусам за период."""
    q = (
        select(Application.status, func.count(Application.id))
        .group_by(Application.status)
    )
    q = _application_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return {row[0]: row[1] for row in r.all()}


async def get_application_success_rate(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> float:
    """Доля завершённых успешно (completed) за период, в процентах."""
    total = await get_total_applications(session, start_date, end_date)
    if total == 0:
        return 0.0
    q = select(func.count(Application.id)).where(Application.status == STATUS_COMPLETED)
    q = _application_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    completed = int(r.scalar() or 0)
    return (completed / total) * 100.0


async def get_average_processing_time(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> float:
    """Среднее время обработки заявки (от started_at до completed_at) в секундах."""
    # (julianday(completed_at) - julianday(started_at)) * 86400 = секунды
    q = (
        select(
            func.avg(
                (func.julianday(Application.completed_at) - func.julianday(Application.started_at))
                * 86400
            )
        )
        .where(Application.status.in_([STATUS_COMPLETED, STATUS_REJECTED]))
        .where(Application.started_at.isnot(None))
        .where(Application.completed_at.isnot(None))
    )
    q = _application_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    val = r.scalar()
    return float(val) if val is not None else 0.0


async def get_average_queue_time(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> float:
    """Среднее время в очереди (от created_at до started_at) в секундах."""
    q = (
        select(
            func.avg(
                (func.julianday(Application.started_at) - func.julianday(Application.created_at))
                * 86400
            )
        )
        .where(Application.started_at.isnot(None))
    )
    q = _application_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    val = r.scalar()
    return float(val) if val is not None else 0.0


async def get_total_users(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> int:
    """Количество пользователей, зарегистрированных за период."""
    q = select(func.count(User.user_id))
    q = _user_date_filter(q, start_date, end_date)
    r = await session.execute(q)
    return int(r.scalar() or 0)


async def get_active_users(session: AsyncSession, days: int = 30) -> int:
    """Количество пользователей с активностью (заявка или транзакция) за последние N дней."""
    since = datetime.utcnow() - timedelta(days=days)
    # Пользователи с заявкой или транзакцией после since
    app_users = select(func.count(func.distinct(Application.user_id))).where(
        Application.created_at >= since
    )
    tx_users = select(func.count(func.distinct(Transaction.user_id))).where(
        Transaction.created_at >= since
    )
    r1 = await session.execute(app_users)
    r2 = await session.execute(tx_users)
    c1 = int(r1.scalar() or 0)
    c2 = int(r2.scalar() or 0)
    # Приближение: объединение через подзапрос (уникальные user_id)
    sub = (
        select(Application.user_id).where(Application.created_at >= since)
        .union(select(Transaction.user_id).where(Transaction.created_at >= since))
    ).subquery()
    r = await session.execute(select(func.count(func.distinct(sub.c.user_id))))
    return int(r.scalar() or 0)


async def get_users_by_role(session: AsyncSession) -> dict[str, int]:
    """Количество пользователей по ролям."""
    q = select(User.role, func.count(User.user_id)).group_by(User.role)
    r = await session.execute(q)
    return {row[0]: row[1] for row in r.all()}


async def get_users_by_source(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source_prefix: str | None = None,
) -> dict[str, int]:
    """Количество пользователей по источнику трафика. NULL источник считаем как 'direct'."""
    source_col = func.coalesce(User.traffic_source, "direct")
    q = select(source_col, func.count(User.user_id)).group_by(source_col)
    q = _user_date_filter(q, start_date, end_date)
    if source_prefix:
        q = q.where(User.traffic_source.isnot(None), User.traffic_source.startswith(source_prefix))
    r = await session.execute(q)
    return {row[0] or "direct": row[1] for row in r.all()}


def _tx_in_period(start_date: datetime | None, end_date: datetime | None):
    """Условие: транзакция-депозит в периоде."""
    c = Transaction.type == TRANSACTION_DEPOSIT
    if start_date is not None:
        c = c & (Transaction.created_at >= start_date)
    if end_date is not None:
        c = c & (Transaction.created_at <= end_date)
    return c


def _app_in_period(start_date: datetime | None, end_date: datetime | None):
    """Условие: заявка в периоде."""
    c = Application.id.isnot(None)
    if start_date is not None:
        c = c & (Application.created_at >= start_date)
    if end_date is not None:
        c = c & (Application.created_at <= end_date)
    return c


async def get_traffic_source_stats(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source_prefix: str | None = None,
) -> dict[str, Any]:
    """
    Статистика по источникам трафика: реги, активные, заявки, депозиты, доход.
    Выручка и число депозитов считаются отдельным запросом (без джойна с Application),
    иначе один депозит при нескольких заявках считался бы многократно.
    """
    source_col = func.coalesce(User.traffic_source, "direct")
    tx_ok = _tx_in_period(start_date, end_date)
    app_ok = _app_in_period(start_date, end_date)
    active_case = case(((tx_ok | app_ok), User.user_id), else_=None)
    with_deposit_case = case((tx_ok, User.user_id), else_=None)
    with_app_case = case((app_ok, User.user_id), else_=None)

    q_activity = (
        select(
            source_col.label("source"),
            func.count(func.distinct(User.user_id)).label("users"),
            func.count(func.distinct(active_case)).label("active"),
            func.count(func.distinct(with_deposit_case)).label("with_deposit"),
            func.count(func.distinct(with_app_case)).label("with_application"),
        )
        .outerjoin(Transaction, User.user_id == Transaction.user_id)
        .outerjoin(Application, User.user_id == Application.user_id)
    )
    q_activity = _user_date_filter(q_activity, start_date, end_date)
    if source_prefix:
        q_activity = q_activity.where(
            User.traffic_source.isnot(None),
            User.traffic_source.startswith(source_prefix),
        )
    q_activity = q_activity.group_by(source_col)
    r_activity = await session.execute(q_activity)
    activity_rows = {row.source or "direct": row for row in r_activity.all()}

    q_revenue = (
        select(
            source_col.label("source"),
            func.sum(Transaction.amount).label("revenue"),
            func.count(Transaction.id).label("deposits_count"),
        )
        .join(Transaction, (User.user_id == Transaction.user_id) & tx_ok)
    )
    q_revenue = _user_date_filter(q_revenue, start_date, end_date)
    if source_prefix:
        q_revenue = q_revenue.where(
            User.traffic_source.isnot(None),
            User.traffic_source.startswith(source_prefix),
        )
    q_revenue = q_revenue.group_by(source_col)
    r_revenue = await session.execute(q_revenue)
    revenue_rows = {row.source or "direct": row for row in r_revenue.all()}

    all_sources = set(activity_rows) | set(revenue_rows)
    stats_data: dict[str, Any] = {}
    for src in all_sources:
        a = activity_rows.get(src)
        rev = revenue_rows.get(src)
        stats_data[src] = {
            "users": int(a.users or 0) if a else 0,
            "new_users": int(a.users or 0) if a else 0,
            "active": int(a.active or 0) if a else 0,
            "with_deposit": int(a.with_deposit or 0) if a else 0,
            "with_application": int(a.with_application or 0) if a else 0,
            "deposits_count": int(rev.deposits_count or 0) if rev else 0,
            "revenue": int(rev.revenue or 0) if rev else 0,
        }
    return stats_data


async def get_top_sources_by_revenue(
    session: AsyncSession,
    limit: int = 10,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Топ источников по доходу."""
    stats = await get_traffic_source_stats(session, start_date, end_date, source_prefix)
    sorted_sources = sorted(
        stats.items(),
        key=lambda x: x[1]["revenue"],
        reverse=True,
    )
    return [
        {
            "source": source,
            "revenue": data["revenue"],
            "users": data["users"],
            "average_ltv": (data["revenue"] / data["users"]) if data["users"] else 0,
        }
        for source, data in sorted_sources[:limit]
    ]


async def get_top_sources_by_users(
    session: AsyncSession,
    limit: int = 10,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Топ источников по пользователям."""
    stats = await get_traffic_source_stats(session, start_date, end_date, source_prefix)
    sorted_sources = sorted(
        stats.items(),
        key=lambda x: x[1]["users"],
        reverse=True,
    )
    return [
        {"source": source, "users": data["users"], "revenue": data["revenue"]}
        for source, data in sorted_sources[:limit]
    ]


async def get_top_sources_by_conversion(
    session: AsyncSession,
    limit: int = 10,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    source_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Топ источников по конверсии (доля с депозитом от регов)."""
    stats = await get_traffic_source_stats(session, start_date, end_date, source_prefix)
    def conv_rate(item):
        s, d = item
        return (d["with_deposit"] / d["users"] * 100.0) if d["users"] else 0.0
    sorted_sources = sorted(
        stats.items(),
        key=conv_rate,
        reverse=True,
    )
    return [
        {
            "source": source,
            "conversion_rate": conv_rate((source, data)),
            "users": data["users"],
            "with_deposit": data["with_deposit"],
        }
        for source, data in sorted_sources[:limit]
    ]


async def get_costs_by_source(session: AsyncSession) -> dict[str, float]:
    """Затраты по источникам (RUB) из таблицы traffic_source_costs."""
    q = select(TrafficSourceCost.source, TrafficSourceCost.cost_rub)
    r = await session.execute(q)
    return {row[0]: float(row[1] or 0) for row in r.all()}


async def get_top_sources_paginated(
    session: AsyncSession,
    start_date: datetime | None,
    end_date: datetime | None,
    source_prefix: str | None = None,
    page: int = 1,
    per_page: int = 3,
) -> tuple[list[dict[str, Any]], int]:
    """
    Список источников для одной страницы отчёта и общее число страниц.
    Возвращает (sources_for_page, total_pages).
    """
    stats = await get_traffic_source_stats(session, start_date, end_date, source_prefix)
    sources_sorted = sorted(
        stats.keys(),
        key=lambda s: stats[s]["revenue"],
        reverse=True,
    )
    total = len(sources_sorted)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    page_sources = sources_sorted[start_idx : start_idx + per_page]
    return (
        [{"source": s, **stats[s]} for s in page_sources],
        total_pages,
    )


async def get_channel_sources(session: AsyncSession) -> dict[str, list[str]]:
    """Канал -> список источников (тегов). Для отчёта «По каналам»."""
    q = (
        select(TrafficChannel.name, TrafficChannelSource.source)
        .join(TrafficChannelSource, TrafficChannel.id == TrafficChannelSource.channel_id)
        .order_by(TrafficChannel.name, TrafficChannelSource.source)
    )
    r = await session.execute(q)
    result: dict[str, list[str]] = {}
    for name, source in r.all():
        result.setdefault(name, []).append(source)
    return result


def _channel_sources_from_ads(by_source: dict[str, Any]) -> dict[str, list[str]]:
    """Строит группировку канал -> список источников из ключей by_source по правилу ads_{{channel}}{{nn}}."""
    channel_sources: dict[str, list[str]] = {}
    for source in by_source:
        channel = extract_channel_from_source(source)
        if channel is not None:
            channel_sources.setdefault(channel, []).append(source)
    return channel_sources


async def get_traffic_channel_stats(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """
    Статистика по каналам: агрегация get_traffic_source_stats по каналам.
    Каналы строятся из источников формата ads_{{channel}}{{nn}} (метка канала трафика).
    Дополнительно учитываются каналы из таблицы traffic_channel_sources.
    """
    by_source = await get_traffic_source_stats(session, start_date, end_date)
    channel_sources = _channel_sources_from_ads(by_source)
    table_sources = await get_channel_sources(session)
    for ch, sources in table_sources.items():
        channel_sources.setdefault(ch, []).extend(sources)
    if not channel_sources:
        return {}
    result: dict[str, Any] = {}
    for channel_name, sources in channel_sources.items():
        users = active = with_deposit = with_application = 0
        deposits_count = revenue = 0
        for src in sources:
            data = by_source.get(src)
            if not data:
                continue
            users += data.get("users", 0) or 0
            active += data.get("active", 0) or 0
            with_deposit += data.get("with_deposit", 0) or 0
            with_application += data.get("with_application", 0) or 0
            deposits_count += data.get("deposits_count", 0) or 0
            revenue += data.get("revenue", 0) or 0
        result[channel_name] = {
            "users": users,
            "new_users": users,
            "active": active,
            "with_deposit": with_deposit,
            "with_application": with_application,
            "deposits_count": deposits_count,
            "revenue": revenue,
            "tags_count": len(sources),
        }
    return result


async def get_costs_by_channel(session: AsyncSession) -> dict[str, float]:
    """Затраты по каналам (RUB): сумма затрат всех источников канала. Учитываются авто-каналы из ads_* и таблица."""
    costs_by_source = await get_costs_by_source(session)
    table_sources = await get_channel_sources(session)
    source_to_channel_table: dict[str, str] = {}
    for ch, sources in table_sources.items():
        for s in sources:
            source_to_channel_table.setdefault(s, ch)
    result: dict[str, float] = {}
    for source, cost in costs_by_source.items():
        ch = extract_channel_from_source(source) or source_to_channel_table.get(source)
        if ch:
            result[ch] = result.get(ch, 0.0) + cost
    return result


async def get_channels_paginated(
    session: AsyncSession,
    start_date: datetime | None,
    end_date: datetime | None,
    page: int = 1,
    per_page: int = 3,
) -> tuple[list[dict[str, Any]], int]:
    """
    Список каналов для одной страницы отчёта «По каналам» и общее число страниц.
    """
    stats = await get_traffic_channel_stats(session, start_date, end_date)
    channels_sorted = sorted(
        stats.keys(),
        key=lambda c: stats[c]["revenue"],
        reverse=True,
    )
    total = len(channels_sorted)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * per_page
    page_channels = channels_sorted[start_idx : start_idx + per_page]
    return (
        [{"channel": c, **stats[c]} for c in page_channels],
        total_pages,
    )


async def get_campaign_stats(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Статистика по кампаниям. Заглушка при отсутствии UTM."""
    return {}

