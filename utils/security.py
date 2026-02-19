"""
Утилиты безопасности для бота
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import Message, CallbackQuery
    from database.models import User

from config import ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN


def validate_amount(amount: int, min_amount: int = 0, max_amount: int | None = None) -> tuple[bool, str]:
    """
    Валидация суммы платежа (в звёздах).
    
    Returns:
        (is_valid, error_message)
    """
    if amount < min_amount:
        return False, f"Минимальная сумма: {min_amount}⭐"
    
    if max_amount is not None and amount > max_amount:
        return False, f"Максимальная сумма: {max_amount}⭐"
    
    if amount <= 0:
        return False, "Количество звёзд должно быть положительным числом"
    
    return True, ""


def validate_user_id(user_id_str: str) -> tuple[bool, int | None, str]:
    """
    Валидация user_id из строки.
    
    Returns:
        (is_valid, user_id, error_message)
    """
    try:
        user_id = int(user_id_str)
        if user_id <= 0:
            return False, None, "User ID должен быть положительным числом"
        return True, user_id, ""
    except ValueError:
        return False, None, "User ID должен быть числом"


def validate_role(role: str) -> tuple[bool, str]:
    """
    Валидация роли пользователя.
    
    Returns:
        (is_valid, error_message)
    """
    valid_roles = (ROLE_USER, ROLE_MODERATOR, ROLE_ADMIN)
    if role.lower() not in valid_roles:
        return False, f"Неверная роль. Доступные: {', '.join(valid_roles)}"
    return True, ""


def check_role_access(user: User, required_roles: tuple[str, ...]) -> bool:
    """
    Проверка доступа пользователя к функциям, требующим определённые роли.
    
    Args:
        user: Объект пользователя из БД
        required_roles: Кортеж ролей, которые имеют доступ
        
    Returns:
        True если доступ разрешён, False иначе
    """
    return user.role in required_roles


def is_moderator_or_admin(user: User) -> bool:
    """Проверка, является ли пользователь модератором или админом"""
    return check_role_access(user, (ROLE_MODERATOR, ROLE_ADMIN))


def is_admin_only(user: User) -> bool:
    """Проверка, является ли пользователь администратором"""
    return check_role_access(user, (ROLE_ADMIN,))
