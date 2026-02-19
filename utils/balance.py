"""
Работа с балансом пользователей.

Здесь реализуются удобные обёртки вокруг запросов к БД
для пополнения и чтения баланса. Сейчас используется
тестовый режим пополнения без интеграции с платёжными API.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import get_or_create_user, change_balance


async def get_balance(session: AsyncSession, user_id: int) -> int:
    """
    Получить текущий баланс пользователя (в звёздах).
    """
    user = await get_or_create_user(session, user_id=user_id)
    return int(user.balance)


async def test_deposit(
    session: AsyncSession,
    user_id: int,
    amount: int,
    transaction_id: str | None = None,
) -> int:
    """
    Тестовое пополнение баланса без реального платёжного API (в звёздах).

    В реальной интеграции здесь должна быть проверка статуса
    платежа у платёжного провайдера.
    """
    description_parts = [f"Тестовое пополнение баланса на {amount}⭐"]
    if transaction_id:
        description_parts.append(f"ID транзакции: {transaction_id}")
    description = " | ".join(description_parts)

    user = await get_or_create_user(session, user_id=user_id)

    # Используем общую функцию изменения баланса с типом deposit
    await change_balance(
        session=session,
        user=user,
        amount=amount,
        description=description,
        is_deposit=True,
    )

    return int(user.balance)


async def deposit_stars(
    session: AsyncSession,
    user_id: int,
    amount: int,
    transaction_id: str | None = None,
) -> int:
    """
    Пополнение баланса через Telegram Stars (реальная оплата).
    
    Args:
        session: Сессия БД
        user_id: ID пользователя
        amount: Количество звёзд
        transaction_id: ID транзакции от Telegram
        
    Returns:
        Новый баланс пользователя
    """
    description_parts = [f"Пополнение баланса через Telegram Stars: {amount}⭐"]
    if transaction_id:
        description_parts.append(f"ID транзакции: {transaction_id}")
    description = " | ".join(description_parts)

    user = await get_or_create_user(session, user_id=user_id)

    # Используем общую функцию изменения баланса с типом deposit
    await change_balance(
        session=session,
        user=user,
        amount=amount,
        description=description,
        is_deposit=True,
    )

    return int(user.balance)

