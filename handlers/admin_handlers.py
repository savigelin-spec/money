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
from keyboards.admin_keyboards import (
    get_admin_panel_keyboard,
    get_admin_back_keyboard,
    get_admin_role_keyboard,
)
from utils.security import is_admin_only, validate_user_id, validate_role
from utils.user_messages import update_user_main_message
from handlers.states import AdminStates

logger = logging.getLogger(__name__)
router = Router()

ADMIN_PANEL_TITLE = "👑 Панель администратора\n\nВыберите действие:"


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


@router.callback_query(F.data == "go_to_admin_panel")
async def callback_go_to_admin_panel(callback: CallbackQuery, state: FSMContext):
    """Переход в панель администратора из главного меню"""
    await state.clear()
    if not await check_admin_access(callback):
        return
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text=ADMIN_PANEL_TITLE,
        reply_markup=get_admin_panel_keyboard(),
    )
    await callback.answer()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    """Команда для доступа к панели администратора (то же главное сообщение)"""
    await state.clear()
    if not await check_admin_access(message):
        return
    await update_user_main_message(
        bot=message.bot,
        user_id=message.from_user.id,
        text=ADMIN_PANEL_TITLE,
        reply_markup=get_admin_panel_keyboard(),
    )


@router.callback_query(F.data == "admin_list_users")
async def callback_admin_list_users(callback: CallbackQuery, state: FSMContext):
    """Список пользователей (последние 20)."""
    await state.clear()
    if not await check_admin_access(callback):
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
                await update_user_main_message(
                    bot=callback.bot,
                    user_id=callback.from_user.id,
                    text="📋 Пользователей пока нет",
                    reply_markup=get_admin_back_keyboard(),
                )
            else:
                users_text = "📋 Последние 20 пользователей:\n\n"
                for user in users:
                    users_text += (
                        f"ID: {user.user_id} | "
                        f"@{user.username or 'нет'} | "
                        f"Роль: {user.role} | "
                        f"Баланс: {user.balance}⭐\n"
                    )
                if len(users_text) > 4000:
                    users_text = users_text[:4000] + "\n\n... (показаны первые 20)"
                await update_user_main_message(
                    bot=callback.bot,
                    user_id=callback.from_user.id,
                    text=users_text,
                    reply_markup=get_admin_back_keyboard(),
                )
            break
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def callback_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Заглушка: Рассылка."""
    await state.clear()
    if not await check_admin_access(callback):
        return
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="📢 Рассылка\n\nВ разработке. Здесь будет рассылка сообщений пользователям.",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_settings")
async def callback_admin_settings(callback: CallbackQuery, state: FSMContext):
    """Заглушка: Настройки бота."""
    await state.clear()
    if not await check_admin_access(callback):
        return
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="⚙️ Настройки бота\n\nВ разработке.",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_actions_log")
async def callback_admin_actions_log(callback: CallbackQuery, state: FSMContext):
    """Заглушка: Лог действий."""
    await state.clear()
    if not await check_admin_access(callback):
        return
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="📜 Лог действий\n\nВ разработке.",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_user_info")
async def callback_admin_user_info(callback: CallbackQuery, state: FSMContext):
    """Инфо о пользователе — запрос user_id."""
    if not await check_admin_access(callback):
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(admin_action="user_info")
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="👤 Инфо о пользователе\n\nВведите user_id (число):",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_role")
async def callback_admin_set_role(callback: CallbackQuery, state: FSMContext):
    """Назначить роль — запрос user_id."""
    if not await check_admin_access(callback):
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(admin_action="set_role")
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="✏️ Назначить роль\n\nВведите user_id (число):",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_set_moderator")
async def callback_admin_set_moderator(callback: CallbackQuery, state: FSMContext):
    """Назначить модератора — запрос user_id."""
    if not await check_admin_access(callback):
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(admin_action="set_moderator")
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="➕ Назначить модератора\n\nВведите user_id (число):",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_remove_moderator")
async def callback_admin_remove_moderator(callback: CallbackQuery, state: FSMContext):
    """Снять модератора — запрос user_id."""
    if not await check_admin_access(callback):
        return
    await state.set_state(AdminStates.waiting_user_id)
    await state.update_data(admin_action="remove_moderator")
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="➖ Снять модератора\n\nВведите user_id (число):",
        reply_markup=get_admin_back_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_role_"))
async def callback_admin_role_select(callback: CallbackQuery, state: FSMContext):
    """Выбор роли (user / moderator / admin) после ввода user_id."""
    if not await check_admin_access(callback):
        return
    if await state.get_state() != AdminStates.waiting_role.state:
        await callback.answer()
        return
    role_map = {"admin_role_user": ROLE_USER, "admin_role_moderator": ROLE_MODERATOR, "admin_role_admin": ROLE_ADMIN}
    new_role = role_map.get(callback.data)
    if not new_role:
        await callback.answer()
        return
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    await state.clear()
    if target_user_id is None:
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="❌ Сессия истекла. Начните заново.",
            reply_markup=get_admin_back_keyboard(),
        )
        await callback.answer()
        return
    try:
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            old_role = target_user.role
            target_user.role = new_role
            await session.commit()
            logger.info(
                f"Admin {callback.from_user.id} changed role for user {target_user_id} "
                f"from {old_role} to {new_role}"
            )
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=(
                    f"✅ Роль пользователя {target_user_id} изменена:\n"
                    f"Было: {old_role}\nСтало: {new_role}"
                ),
                reply_markup=get_admin_back_keyboard(),
            )
            break
    except Exception as e:
        logger.error(f"Ошибка при изменении роли: {e}")
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_back_keyboard(),
        )
    await callback.answer()


@router.message(AdminStates.waiting_user_id, F.text)
async def admin_message_waiting_user_id(message: Message, state: FSMContext):
    """Обработка введённого user_id в админских действиях."""
    if not await check_admin_access(message):
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return
    is_valid_id, target_user_id, error_msg = validate_user_id(text)
    if not is_valid_id or target_user_id is None:
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"❌ {error_msg}",
            reply_markup=get_admin_back_keyboard(),
        )
        return
    data = await state.get_data()
    action = data.get("admin_action")
    if action == "user_info":
        await state.clear()
        try:
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
                await update_user_main_message(
                    bot=message.bot,
                    user_id=message.from_user.id,
                    text=info_text,
                    reply_markup=get_admin_back_keyboard(),
                )
                break
        except Exception as e:
            logger.error(f"Ошибка при получении информации о пользователе: {e}")
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ Ошибка: {e}",
                reply_markup=get_admin_back_keyboard(),
            )
        return
    if action == "set_role":
        await state.set_state(AdminStates.waiting_role)
        await state.update_data(target_user_id=target_user_id)
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"✏️ Выберите роль для пользователя {target_user_id}:",
            reply_markup=get_admin_role_keyboard(),
        )
        return
    if action == "set_moderator":
        await state.clear()
        try:
            async for session in get_session():
                target_user = await get_or_create_user(session, user_id=target_user_id)
                target_user.role = ROLE_MODERATOR
                await session.commit()
                logger.info(f"Admin {message.from_user.id} set moderator role for user {target_user_id}")
                await update_user_main_message(
                    bot=message.bot,
                    user_id=message.from_user.id,
                    text=f"✅ Пользователь {target_user_id} назначен модератором",
                    reply_markup=get_admin_back_keyboard(),
                )
                break
        except Exception as e:
            logger.error(f"Ошибка при назначении модератора: {e}")
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ Ошибка: {e}",
                reply_markup=get_admin_back_keyboard(),
            )
        return
    if action == "remove_moderator":
        await state.clear()
        try:
            async for session in get_session():
                target_user = await get_or_create_user(session, user_id=target_user_id)
                if target_user.role != ROLE_MODERATOR:
                    await update_user_main_message(
                        bot=message.bot,
                        user_id=message.from_user.id,
                        text=f"❌ Пользователь {target_user_id} не является модератором",
                        reply_markup=get_admin_back_keyboard(),
                    )
                    await session.rollback()
                    return
                target_user.role = ROLE_USER
                await session.commit()
                logger.info(f"Admin {message.from_user.id} removed moderator role from user {target_user_id}")
                await update_user_main_message(
                    bot=message.bot,
                    user_id=message.from_user.id,
                    text=f"✅ Роль модератора убрана у пользователя {target_user_id}",
                    reply_markup=get_admin_back_keyboard(),
                )
                break
        except Exception as e:
            logger.error(f"Ошибка при снятии модератора: {e}")
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ Ошибка: {e}",
                reply_markup=get_admin_back_keyboard(),
            )


@router.message(Command("set_role"))
async def cmd_set_role(message: Message):
    """Назначить роль пользователю"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=(
                    "❌ Неверный формат команды.\n"
                    "Использование: /set_role &lt;user_id&gt; &lt;role&gt;\n"
                    "Роли: user, moderator, admin"
                ),
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ {error_msg}",
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        new_role = parts[2].lower()
        
        # Валидация роли
        is_valid_role, error_msg = validate_role(new_role)
        if not is_valid_role:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ {error_msg}",
                reply_markup=get_admin_panel_keyboard()
            )
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
            
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=(
                    f"✅ Роль пользователя {target_user_id} изменена:\n"
                    f"Было: {old_role}\n"
                    f"Стало: {new_role}"
                ),
                reply_markup=get_admin_panel_keyboard()
            )
            return
            
    except ValueError:
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text="❌ Неверный формат user_id. Должно быть число.",
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении роли: {e}")
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_panel_keyboard()
        )


@router.message(Command("set_moderator"))
async def cmd_set_moderator(message: Message):
    """Быстрая команда для назначения модератора"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=(
                    "❌ Неверный формат команды.\n"
                    "Использование: /set_moderator &lt;user_id&gt;"
                ),
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ {error_msg}",
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            old_role = target_user.role
            target_user.role = ROLE_MODERATOR
            await session.commit()
            
            logger.info(
                f"Admin {message.from_user.id} set moderator role for user {target_user_id}"
            )
            
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"✅ Пользователь {target_user_id} назначен модератором",
                reply_markup=get_admin_panel_keyboard()
            )
            return
            
    except ValueError:
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text="❌ Неверный формат user_id. Должно быть число.",
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при назначении модератора: {e}")
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_panel_keyboard()
        )


@router.message(Command("remove_moderator"))
async def cmd_remove_moderator(message: Message):
    """Убрать роль модератора"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=(
                    "❌ Неверный формат команды.\n"
                    "Использование: /remove_moderator &lt;user_id&gt;"
                ),
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ {error_msg}",
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        async for session in get_session():
            target_user = await get_or_create_user(session, user_id=target_user_id)
            
            if target_user.role != ROLE_MODERATOR:
                await update_user_main_message(
                    bot=message.bot,
                    user_id=message.from_user.id,
                    text=f"❌ Пользователь {target_user_id} не является модератором",
                    reply_markup=get_admin_panel_keyboard()
                )
                await session.rollback()
                return
            
            target_user.role = ROLE_USER
            await session.commit()
            
            logger.info(
                f"Admin {message.from_user.id} removed moderator role from user {target_user_id}"
            )
            
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"✅ Роль модератора убрана у пользователя {target_user_id}",
                reply_markup=get_admin_panel_keyboard()
            )
            return
            
    except ValueError:
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text="❌ Неверный формат user_id. Должно быть число.",
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при удалении роли модератора: {e}")
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_panel_keyboard()
        )


@router.message(Command("user_info"))
async def cmd_user_info(message: Message):
    """Информация о пользователе"""
    if not await check_admin_access(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=(
                    "❌ Неверный формат команды.\n"
                    "Использование: /user_info &lt;user_id&gt;"
                ),
                reply_markup=get_admin_panel_keyboard()
            )
            return
        
        # Валидация user_id
        is_valid_id, target_user_id, error_msg = validate_user_id(parts[1])
        if not is_valid_id:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=f"❌ {error_msg}",
                reply_markup=get_admin_panel_keyboard()
            )
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
            
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=info_text,
                reply_markup=get_admin_panel_keyboard()
            )
            return
            
    except ValueError:
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text="❌ Неверный формат user_id. Должно быть число.",
            reply_markup=get_admin_panel_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при получении информации о пользователе: {e}")
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_panel_keyboard()
        )


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
                await update_user_main_message(
                    bot=message.bot,
                    user_id=message.from_user.id,
                    text="📋 Пользователей пока нет",
                    reply_markup=get_admin_panel_keyboard()
                )
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
            
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text=users_text,
                reply_markup=get_admin_panel_keyboard()
            )
            return
            
    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text=f"❌ Ошибка: {e}",
            reply_markup=get_admin_panel_keyboard()
        )
