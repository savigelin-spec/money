"""
Обработчики для администраторов
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ROLE_ADMIN, ROLE_MODERATOR, ROLE_USER
from database.db import get_session
from database.queries import get_or_create_user, get_user_applications
from keyboards.user_keyboards import get_back_to_menu_keyboard
from utils.security import is_admin_only, validate_user_id, validate_role

logger = logging.getLogger(__name__)
router = Router()


def is_admin(user) -> bool:
    """Проверка, является ли пользователь администратором"""
    return is_admin_only(user)


async def check_admin_access(callback_or_message) -> bool:
    """Проверка доступа администратора"""
    user_id = callback_or_message.from_user.id
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=user_id)
        await session.commit()
        
        if not is_admin(user):
            if isinstance(callback_or_message, CallbackQuery):
                await callback_or_message.answer("❌ У вас нет прав администратора", show_alert=True)
            else:
                await callback_or_message.answer("❌ У вас нет прав администратора")
            return False
        return True


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Команда для доступа к панели администратора"""
    await state.clear()
    
    if not await check_admin_access(message):
        return
    
    admin_text = (
        "👑 Панель администратора\n\n"
        "Доступные команды:\n"
        "/set_role &lt;user_id&gt; &lt;role&gt; — назначить роль\n"
        "/list_users — список пользователей\n"
        "/user_info &lt;user_id&gt; — информация о пользователе\n"
        "/set_moderator &lt;user_id&gt; — назначить модератора\n"
        "/remove_moderator &lt;user_id&gt; — снять модератора\n\n"
        "Роли: user, moderator, admin"
    )
    await message.answer(admin_text)


@router.message(Command("set_role"))
async def cmd_set_role(message: Message):
    """Назначить роль пользователю"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Использование: /set_role &lt;user_id&gt; &lt;role&gt;\n"
                "Роли: user, moderator, admin"
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await message.answer(f"❌ {error_msg}")
            return
        
        new_role = parts[2].lower()
        
        # Валидация роли
        is_valid_role, error_msg = validate_role(new_role)
        if not is_valid_role:
            await message.answer(f"❌ {error_msg}")
            return
        
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            old_role = target_user.role
            target_user.role = new_role
            await session.commit()
            
            logger.info(
                f"Admin {message.from_user.id} changed role for user {target_user_id} "
                f"from {old_role} to {new_role}"
            )
            
            await message.answer(
                f"✅ Роль пользователя {target_user_id} изменена:\n"
                f"Было: {old_role}\n"
                f"Стало: {new_role}"
            )
            return
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Должно быть число.")
    except Exception as e:
        logger.error(f"Ошибка при изменении роли: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("set_moderator"))
async def cmd_set_moderator(message: Message):
    """Быстрая команда для назначения модератора"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Использование: /set_moderator &lt;user_id&gt;"
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await message.answer(f"❌ {error_msg}")
            return
        
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            old_role = target_user.role
            target_user.role = ROLE_MODERATOR
            await session.commit()
            
            logger.info(
                f"Admin {message.from_user.id} set moderator role for user {target_user_id}"
            )
            
            await message.answer(
                f"✅ Пользователь {target_user_id} назначен модератором"
            )
            return
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Должно быть число.")
    except Exception as e:
        logger.error(f"Ошибка при назначении модератора: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("remove_moderator"))
async def cmd_remove_moderator(message: Message):
    """Убрать роль модератора"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Использование: /remove_moderator &lt;user_id&gt;"
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await message.answer(f"❌ {error_msg}")
            return
        
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            
            if target_user.role != ROLE_MODERATOR:
                await message.answer(
                    f"❌ Пользователь {target_user_id} не является модератором"
                )
                await session.rollback()
                return
            
            target_user.role = ROLE_USER
            await session.commit()
            
            logger.info(
                f"Admin {message.from_user.id} removed moderator role from user {target_user_id}"
            )
            
            await message.answer(
                f"✅ Роль модератора убрана у пользователя {target_user_id}"
            )
            return
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Должно быть число.")
    except Exception as e:
        logger.error(f"Ошибка при удалении роли модератора: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("user_info"))
async def cmd_user_info(message: Message):
    """Информация о пользователе"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer(
                "❌ Неверный формат команды.\n"
                "Использование: /user_info &lt;user_id&gt;"
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await message.answer(f"❌ {error_msg}")
            return
        
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            applications = await get_user_applications(session, target_user_id)
            await session.commit()
            
            info_text = (
                f"👤 Информация о пользователе {target_user_id}\n\n"
                f"Имя: {target_user.first_name or 'Не указано'}\n"
                f"Фамилия: {target_user.last_name or 'Не указано'}\n"
                f"Username: @{target_user.username or 'Не указан'}\n"
                f"Роль: {target_user.role}\n"
                f"Баланс: {target_user.balance}⭐\n"
                f"Заявок: {len(applications)}\n"
                f"Регистрация: {target_user.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
            
            await message.answer(info_text)
            return
            
    except ValueError:
        await message.answer("❌ Неверный формат user_id. Должно быть число.")
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("list_users"))
async def cmd_list_users(message: Message):
    """Список пользователей (только первые 20)"""
    if not await check_admin_access(message):
        return
    
    try:
        from sqlalchemy import select
        from database.models import User
        
        async for session in get_session():
            result = await session.execute(
                select(User).order_by(User.created_at.desc()).limit(20)
            )
            users = result.scalars().all()
            await session.commit()
            
            if not users:
                await message.answer("📋 Пользователей пока нет")
                return
            
            users_text = "📋 Последние 20 пользователей:\n\n"
            for user in users:
                users_text += (
                    f"ID: {user.user_id} | "
                    f"@{user.username or 'нет'} | "
                    f"Роль: {user.role} | "
                    f"Баланс: {user.balance}⭐\n"
                )
            
            # Разбиваем на части, если слишком длинное сообщение
            if len(users_text) > 4000:
                users_text = users_text[:4000] + "\n\n... (показаны первые 20)"
            
            await message.answer(users_text)
            return
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        await message.answer(f"❌ Ошибка: {e}")
