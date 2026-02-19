"""
Логика очереди и расчета времени ожидания
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import DEFAULT_MODERATOR_SESSION_TIME
from database.models import Application, ModeratorStats
from database.queries import get_average_session_time_global


async def calculate_queue_position(
    session: AsyncSession,
    application_id: int
) -> int:
    """
    Рассчитать позицию заявки в очереди.
    Позиция = количество pending заявок, созданных раньше + 1
    """
    result = await session.execute(
        select(Application)
        .where(
            Application.status == "pending",
            Application.id <= application_id
        )
        .order_by(Application.created_at)
    )
    pending_before = result.scalars().all()
    
    # Находим позицию текущей заявки
    position = 1
    for app in pending_before:
        if app.id == application_id:
            break
        position += 1
    
    return position


async def calculate_estimated_wait_time(
    session: AsyncSession,
    queue_position: int
) -> int:
    """
    Рассчитать примерное время ожидания в секундах.
    Формула: (позиция_в_очереди - 1) × среднее_время_сессии
    """
    avg_time = await get_average_session_time_global(
        session,
        DEFAULT_MODERATOR_SESSION_TIME
    )
    
    wait_time = (queue_position - 1) * int(avg_time)
    return max(0, wait_time)  # Не может быть отрицательным


async def update_queue_positions(session: AsyncSession) -> None:
    """
    Обновить позиции всех pending заявок в очереди.
    Вызывается при изменении очереди (новая заявка, модератор взял заявку).
    """
    result = await session.execute(
        select(Application)
        .where(Application.status == "pending")
        .order_by(Application.created_at)
    )
    pending_apps = result.scalars().all()
    
    for index, app in enumerate(pending_apps, start=1):
        app.queue_position = index
        # Пересчитываем время ожидания
        app.estimated_wait_time = await calculate_estimated_wait_time(
            session,
            index
        )
    
    await session.flush()


def format_wait_time(seconds: int) -> str:
    """Форматировать время ожидания в читаемый вид"""
    if seconds < 60:
        return f"{seconds} сек"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes} мин"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if minutes > 0:
            return f"{hours} ч {minutes} мин"
        return f"{hours} ч"
