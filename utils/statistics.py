"""
Агрегация и форматирование статистики.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import (
    get_total_revenue,
    get_total_deposits,
    get_total_withdrawals,
    get_net_revenue,
    get_total_applications,
    get_applications_by_status,
    get_application_success_rate,
    get_average_processing_time,
    get_average_queue_time,
    get_total_users,
    get_active_users,
    get_users_by_role,
    get_traffic_source_stats,
    get_top_sources_by_revenue,
    get_top_sources_by_users,
    get_top_sources_by_conversion,
    get_campaign_stats,
)


class StatisticsPeriod:
    """Периоды для статистики."""

    ALL_TIME = "all_time"
    LAST_30_DAYS = "30_days"
    LAST_7_DAYS = "7_days"
    TODAY = "today"
    CUSTOM = "custom"


def get_date_range(
    period: str,
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
) -> tuple[datetime | None, datetime | None]:
    """Диапазон дат для периода."""
    now = datetime.utcnow()
    if period == StatisticsPeriod.TODAY:
        start = datetime(now.year, now.month, now.day)
        return start, now
    if period == StatisticsPeriod.LAST_7_DAYS:
        return now - timedelta(days=7), now
    if period == StatisticsPeriod.LAST_30_DAYS:
        return now - timedelta(days=30), now
    if period == StatisticsPeriod.CUSTOM:
        return custom_start, custom_end
    return None, None


async def get_financial_stats(
    session: AsyncSession,
    period: str = StatisticsPeriod.ALL_TIME,
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
) -> dict[str, Any]:
    """Финансовая статистика."""
    start_date, end_date = get_date_range(period, custom_start, custom_end)
    total_revenue = await get_total_revenue(session, start_date, end_date)
    total_deposits = await get_total_deposits(session, start_date, end_date)
    total_withdrawals = await get_total_withdrawals(session, start_date, end_date)
    net_revenue = await get_net_revenue(session, start_date, end_date)
    return {
        "total_revenue": total_revenue,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "net_revenue": net_revenue,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
    }


async def get_applications_stats(
    session: AsyncSession,
    period: str = StatisticsPeriod.ALL_TIME,
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
) -> dict[str, Any]:
    """Статистика по заявкам."""
    start_date, end_date = get_date_range(period, custom_start, custom_end)
    total = await get_total_applications(session, start_date, end_date)
    by_status = await get_applications_by_status(session, start_date, end_date)
    success_rate = await get_application_success_rate(session, start_date, end_date)
    avg_processing = await get_average_processing_time(session, start_date, end_date)
    avg_queue = await get_average_queue_time(session, start_date, end_date)
    return {
        "total": total,
        "by_status": by_status,
        "success_rate": success_rate,
        "average_processing_time": avg_processing,
        "average_queue_time": avg_queue,
        "period": period,
    }


async def get_users_stats(
    session: AsyncSession,
    period: str = StatisticsPeriod.ALL_TIME,
    custom_start: datetime | None = None,
    custom_end: datetime | None = None,
) -> dict[str, Any]:
    """Статистика по пользователям."""
    start_date, end_date = get_date_range(period, custom_start, custom_end)
    total = await get_total_users(session, start_date, end_date)
    active = await get_active_users(session, days=30)
    by_role = await get_users_by_role(session)
    return {
        "total": total,
        "active": active,
        "by_role": by_role,
        "period": period,
    }


async def get_comprehensive_stats(
    session: AsyncSession,
    period: str = StatisticsPeriod.ALL_TIME,
) -> dict[str, Any]:
    """Сводная статистика: финансы, заявки, пользователи."""
    financial = await get_financial_stats(session, period)
    applications = await get_applications_stats(session, period)
    users = await get_users_stats(session, period)
    return {
        "financial": financial,
        "applications": applications,
        "users": users,
        "period": period,
    }


async def get_traffic_stats(
    session: AsyncSession,
    period: str = StatisticsPeriod.ALL_TIME,
) -> dict[str, Any]:
    """Статистика по источникам трафика."""
    start_date, end_date = get_date_range(period)
    by_source = await get_traffic_source_stats(session, start_date, end_date)
    top_revenue = await get_top_sources_by_revenue(
        session, limit=10, start_date=start_date, end_date=end_date
    )
    top_users = await get_top_sources_by_users(
        session, limit=10, start_date=start_date, end_date=end_date
    )
    top_conversion = await get_top_sources_by_conversion(
        session, limit=10, start_date=start_date, end_date=end_date
    )
    by_campaign = await get_campaign_stats(session, start_date, end_date)
    return {
        "by_source": by_source,
        "top_by_revenue": top_revenue,
        "top_by_users": top_users,
        "top_by_conversion": top_conversion,
        "by_campaign": by_campaign,
        "period": period,
    }


# --- Форматирование (для UI) ---

def period_display_name(period: str) -> str:
    """Человекочитаемое название периода."""
    names = {
        StatisticsPeriod.TODAY: "День",
        StatisticsPeriod.LAST_7_DAYS: "Неделя",
        StatisticsPeriod.LAST_30_DAYS: "Месяц",
        StatisticsPeriod.ALL_TIME: "Всё время",
    }
    return names.get(period, period)


def format_stars(amount: int) -> str:
    """Форматировать звёзды."""
    return f"{amount:,}⭐"


def format_time(seconds: float) -> str:
    """Секунды в читаемый вид."""
    s = int(seconds)
    if s < 60:
        return f"{s} сек"
    if s < 3600:
        return f"{s // 60} мин {s % 60} сек"
    hours = s // 3600
    minutes = (s % 3600) // 60
    return f"{hours} ч {minutes} мин"


def format_percentage(value: float) -> str:
    """Процент."""
    return f"{value:.1f}%"


def format_financial_stats(stats: dict[str, Any]) -> str:
    """Текст финансовой статистики за период."""
    period = stats.get("period", "период")
    period_label = period_display_name(period)
    text = (
        f"💰 Финансовая статистика ({period_label})\n\n"
        f"📥 Получено звёзд: {format_stars(stats.get('total_revenue', 0))}\n"
        f"📤 Потрачено звёзд: {format_stars(stats.get('total_withdrawals', 0))}\n"
        f"💵 Чистая прибыль: {format_stars(stats.get('net_revenue', 0))}\n"
        f"📊 Количество депозитов: {stats.get('total_deposits', 0)}"
    )
    return text


def format_financial_all_time_block(stats: dict[str, Any]) -> str:
    """Блок «Общие показатели (всё время)» для финансов."""
    return (
        f"\n\n📌 Общие показатели (всё время)\n\n"
        f"📥 Получено звёзд: {format_stars(stats.get('total_revenue', 0))}\n"
        f"📤 Потрачено звёзд: {format_stars(stats.get('total_withdrawals', 0))}\n"
        f"💵 Чистая прибыль: {format_stars(stats.get('net_revenue', 0))}\n"
        f"📊 Количество депозитов: {stats.get('total_deposits', 0)}"
    )


def format_applications_stats(stats: dict[str, Any]) -> str:
    """Текст статистики по заявкам."""
    by_status = stats.get("by_status", {})
    period_label = period_display_name(stats.get("period", ""))
    text = (
        f"📋 Статистика по заявкам ({period_label})\n\n"
        f"Всего заявок: {stats.get('total', 0)}\n"
        f"✅ Завершено: {by_status.get('completed', 0)} ({format_percentage(stats.get('success_rate', 0))})\n"
        f"❌ Отклонено: {by_status.get('rejected', 0)}\n"
        f"⏳ В обработке: {by_status.get('moderating', 0) + by_status.get('pending', 0)}\n\n"
        f"⏱ Среднее время обработки: {format_time(stats.get('average_processing_time', 0))}\n"
        f"⏳ Среднее время в очереди: {format_time(stats.get('average_queue_time', 0))}"
    )
    return text


def format_users_stats(stats: dict[str, Any]) -> str:
    """Текст статистики по пользователям."""
    by_role = stats.get("by_role", {})
    period_label = period_display_name(stats.get("period", ""))
    text = (
        f"👥 Статистика по пользователям ({period_label})\n\n"
        f"Всего пользователей: {stats.get('total', 0)}\n"
        f"🟢 Активных: {stats.get('active', 0)}\n\n"
        f"📊 По ролям:\n"
        f"👤 Пользователи: {by_role.get('user', 0)}\n"
        f"👮 Модераторы: {by_role.get('moderator', 0)}\n"
        f"👑 Администраторы: {by_role.get('admin', 0)}"
    )
    return text


def format_comprehensive_stats(stats: dict[str, Any]) -> str:
    """Текст сводной статистики."""
    financial = stats.get("financial", {})
    applications = stats.get("applications", {})
    users = stats.get("users", {})
    period_label = period_display_name(stats.get("period", ""))
    text = (
        f"📊 Комплексная статистика ({period_label})\n\n"
        f"💰 Финансы:\n"
        f"Доход: {format_stars(financial.get('total_revenue', 0))}\n"
        f"Чистая прибыль: {format_stars(financial.get('net_revenue', 0))}\n\n"
        f"📋 Заявки:\n"
        f"Всего: {applications.get('total', 0)}\n"
        f"Успешных: {format_percentage(applications.get('success_rate', 0))}\n\n"
        f"👥 Пользователи:\n"
        f"Всего: {users.get('total', 0)}\n"
        f"Активных: {users.get('active', 0)}"
    )
    return text


def format_marketing_stats(
    funnel: dict[str, Any],
    ltv: float,
    retention: dict[str, float],
) -> str:
    """Текст маркетинговой статистики."""
    rates = funnel.get("conversion_rates", {})
    text = (
        f"📈 Маркетинговые показатели\n\n"
        f"🎯 Конверсия:\n"
        f"Посетители: {funnel.get('visitors', 0)}\n"
        f"→ Первый депозит: {funnel.get('first_deposit', 0)} ({format_percentage(rates.get('to_deposit', 0))})\n"
        f"→ Первая заявка: {funnel.get('first_application', 0)} ({format_percentage(rates.get('to_application', 0))})\n"
        f"→ Завершённые заявки: {funnel.get('completed_application', 0)} ({format_percentage(rates.get('to_completed', 0))})\n\n"
        f"💰 LTV: средний {format_stars(int(ltv))}\n\n"
        f"🔄 Retention:\n"
    )
    for key, value in retention.items():
        day = key.replace("day_", "")
        text += f"  День {day}: {format_percentage(value)}\n"
    return text


def format_traffic_stats(stats: dict[str, Any]) -> str:
    """Текст статистики по источникам трафика."""
    top_revenue = stats.get("top_by_revenue", [])
    top_users = stats.get("top_by_users", [])
    top_conversion = stats.get("top_by_conversion", [])
    period_label = period_display_name(stats.get("period", ""))
    text = (
        f"🔗 Источники трафика ({period_label})\n\n"
        f"💰 Топ по доходу:\n"
    )
    for i, row in enumerate(top_revenue[:5], 1):
        text += f"{i}. {row.get('source', 'unknown')} — {format_stars(row.get('revenue', 0))}\n"
    text += f"\n📊 Топ по пользователям:\n"
    for i, row in enumerate(top_users[:5], 1):
        text += f"{i}. {row.get('source', 'unknown')} — {row.get('users', 0)} польз.\n"
    text += f"\n🎯 Топ по конверсии:\n"
    for i, row in enumerate(top_conversion[:5], 1):
        text += f"{i}. {row.get('source', 'unknown')} — {format_percentage(row.get('conversion_rate', 0))}\n"
    return text
