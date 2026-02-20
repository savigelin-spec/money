"""
Маркетинговые метрики: конверсия, LTV, CAC, ROI, retention.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import TRANSACTION_DEPOSIT, STATUS_COMPLETED
from database.models import User, Transaction, Application
from database.queries import get_users_by_source


async def get_conversion_funnel(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Воронка конверсии: посетители → депозит → заявка → завершённая заявка."""
    visitors_query = select(func.count(User.user_id))
    if start_date:
        visitors_query = visitors_query.where(User.created_at >= start_date)
    if end_date:
        visitors_query = visitors_query.where(User.created_at <= end_date)
    visitors = (await session.execute(visitors_query)).scalar() or 0

    deposits_query = select(func.count(func.distinct(Transaction.user_id))).where(
        Transaction.type == TRANSACTION_DEPOSIT
    )
    if start_date:
        deposits_query = deposits_query.where(Transaction.created_at >= start_date)
    if end_date:
        deposits_query = deposits_query.where(Transaction.created_at <= end_date)
    first_deposit = (await session.execute(deposits_query)).scalar() or 0

    applications_query = select(func.count(func.distinct(Application.user_id)))
    if start_date:
        applications_query = applications_query.where(Application.created_at >= start_date)
    if end_date:
        applications_query = applications_query.where(Application.created_at <= end_date)
    first_application = (await session.execute(applications_query)).scalar() or 0

    completed_query = select(func.count(func.distinct(Application.user_id))).where(
        Application.status == STATUS_COMPLETED
    )
    if start_date:
        completed_query = completed_query.where(Application.created_at >= start_date)
    if end_date:
        completed_query = completed_query.where(Application.created_at <= end_date)
    completed_application = (await session.execute(completed_query)).scalar() or 0

    conversion_rates: dict[str, float] = {}
    if visitors > 0:
        conversion_rates["to_deposit"] = (first_deposit / visitors) * 100.0
        conversion_rates["to_application"] = (first_application / visitors) * 100.0
        conversion_rates["to_completed"] = (completed_application / visitors) * 100.0
    else:
        conversion_rates = {"to_deposit": 0.0, "to_application": 0.0, "to_completed": 0.0}

    return {
        "visitors": visitors,
        "registered": visitors,
        "first_deposit": first_deposit,
        "first_application": first_application,
        "completed_application": completed_application,
        "conversion_rates": conversion_rates,
    }


async def get_conversion_by_source(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Конверсия по источникам трафика."""
    from sqlalchemy import case

    query = (
        select(
            User.traffic_source,
            func.count(func.distinct(User.user_id)).label("users"),
            func.count(
                func.distinct(
                    case((Transaction.type == TRANSACTION_DEPOSIT, Transaction.user_id))
                )
            ).label("users_with_deposit"),
            func.count(func.distinct(Application.user_id)).label("users_with_application"),
        )
        .outerjoin(Transaction, User.user_id == Transaction.user_id)
        .outerjoin(Application, User.user_id == Application.user_id)
    )
    if start_date:
        query = query.where(User.created_at >= start_date)
    if end_date:
        query = query.where(User.created_at <= end_date)
    query = query.group_by(User.traffic_source)
    result = await session.execute(query)
    conversion_data: dict[str, Any] = {}
    for row in result.all():
        source = row.traffic_source or "unknown"
        users = row.users or 0
        users_with_deposit = row.users_with_deposit or 0
        users_with_application = row.users_with_application or 0
        conversion_data[source] = {
            "users": users,
            "deposits": users_with_deposit,
            "applications": users_with_application,
            "conversion_to_deposit": (users_with_deposit / users * 100.0) if users else 0.0,
            "conversion_to_application": (users_with_application / users * 100.0) if users else 0.0,
        }
    return conversion_data


async def get_average_ltv(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> float:
    """Средний LTV (доход на пользователя за период по зарегистрированным)."""
    users_sub = select(User.user_id)
    if start_date:
        users_sub = users_sub.where(User.created_at >= start_date)
    if end_date:
        users_sub = users_sub.where(User.created_at <= end_date)
    users_sub = users_sub.subquery()
    ltv_sub = (
        select(
            users_sub.c.user_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("user_ltv"),
        )
        .outerjoin(Transaction, users_sub.c.user_id == Transaction.user_id)
        .where(Transaction.type == TRANSACTION_DEPOSIT)
        .group_by(users_sub.c.user_id)
    ).subquery()
    avg_q = select(func.avg(ltv_sub.c.user_ltv))
    result = await session.execute(avg_q)
    val = result.scalar()
    return float(val) if val is not None else 0.0


async def get_ltv_by_source(
    session: AsyncSession,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """LTV по источникам трафика."""
    user_ltv = (
        select(
            User.traffic_source,
            User.user_id,
            func.coalesce(func.sum(Transaction.amount), 0).label("user_ltv"),
        )
        .join(Transaction, User.user_id == Transaction.user_id)
        .where(Transaction.type == TRANSACTION_DEPOSIT)
        .group_by(User.user_id, User.traffic_source)
    )
    if start_date:
        user_ltv = user_ltv.where(User.created_at >= start_date)
    if end_date:
        user_ltv = user_ltv.where(User.created_at <= end_date)
    user_ltv = user_ltv.subquery()
    agg = (
        select(
            user_ltv.c.traffic_source,
            func.count(user_ltv.c.user_id).label("user_count"),
            func.sum(user_ltv.c.user_ltv).label("total_revenue"),
            func.avg(user_ltv.c.user_ltv).label("average_ltv"),
        )
        .group_by(user_ltv.c.traffic_source)
    )
    result = await session.execute(agg)
    ltv_data: dict[str, Any] = {}
    for row in result.all():
        source = row.traffic_source or "unknown"
        ltv_data[source] = {
            "average_ltv": float(row.average_ltv or 0),
            "total_revenue": int(row.total_revenue or 0),
            "user_count": row.user_count or 0,
        }
    return ltv_data


async def get_cac_by_source(
    session: AsyncSession,
    costs: dict[str, int | float],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """CAC по источникам (при известных затратах)."""
    users_by_source = await get_users_by_source(session, start_date, end_date)
    cac_data: dict[str, Any] = {}
    for source, cost in costs.items():
        users = users_by_source.get(source, 0)
        cac_data[source] = {
            "cost": cost,
            "users": users,
            "cac": (cost / users) if users > 0 else 0.0,
        }
    return cac_data


async def get_roi_by_source(
    session: AsyncSession,
    costs: dict[str, int | float],
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """ROI по источникам: (LTV - CAC) / CAC * 100."""
    ltv_by_source = await get_ltv_by_source(session, start_date, end_date)
    cac_by_source = await get_cac_by_source(session, costs, start_date, end_date)
    roi_data: dict[str, Any] = {}
    for source in costs:
        ltv = ltv_by_source.get(source, {}).get("average_ltv", 0.0)
        cac = cac_by_source.get(source, {}).get("cac", 0.0)
        roi = ((ltv - cac) / cac * 100.0) if cac > 0 else 0.0
        roi_data[source] = {"ltv": ltv, "cac": cac, "roi": roi}
    return roi_data


async def get_retention_rate(
    session: AsyncSession,
    days: list[int] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, float]:
    """Retention: доля пользователей, вернувшихся через N дней."""
    from sqlalchemy import union_all

    if days is None:
        days = [1, 3, 7, 14, 30]
    retention_data: dict[str, float] = {}
    now = datetime.utcnow()
    for day in days:
        cutoff = now - timedelta(days=day)
        registered_q = select(func.count(User.user_id)).where(User.created_at <= cutoff)
        if start_date:
            registered_q = registered_q.where(User.created_at >= start_date)
        if end_date:
            registered_q = registered_q.where(User.created_at <= end_date)
        registered = (await session.execute(registered_q)).scalar() or 0
        q1 = select(Transaction.user_id).where(Transaction.created_at >= cutoff)
        q2 = select(Application.user_id).where(Application.created_at >= cutoff)
        u = union_all(q1, q2).subquery()
        active_q = select(func.count(func.distinct(u.c.user_id))).select_from(u)
        active = (await session.execute(active_q)).scalar() or 0
        retention_data[f"day_{day}"] = (active / registered * 100.0) if registered > 0 else 0.0
    return retention_data


async def get_churn_rate(
    session: AsyncSession,
    days: int = 30,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> float:
    """Churn: доля пользователей без активности более N дней."""
    from sqlalchemy import union_all

    cutoff = datetime.utcnow() - timedelta(days=days)
    total_q = select(func.count(User.user_id))
    if start_date:
        total_q = total_q.where(User.created_at >= start_date)
    if end_date:
        total_q = total_q.where(User.created_at <= end_date)
    total = (await session.execute(total_q)).scalar() or 0
    q1 = select(Transaction.user_id).where(Transaction.created_at >= cutoff)
    q2 = select(Application.user_id).where(Application.created_at >= cutoff)
    u = union_all(q1, q2).subquery()
    active_q = select(func.count(func.distinct(u.c.user_id))).select_from(u)
    active = (await session.execute(active_q)).scalar() or 0
    churned = total - active
    return (churned / total * 100.0) if total > 0 else 0.0
