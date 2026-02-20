"""
Обработчики для модераторов
"""
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import ROLE_MODERATOR, ROLE_ADMIN, STATUS_COMPLETED, STATUS_REJECTED
from utils.security import is_moderator_or_admin
from database.db import get_session
from database.queries import (
    get_or_create_user,
    get_pending_applications,
    get_application_by_id,
    assign_moderator_to_application,
    create_moderation_session,
    get_active_moderation_sessions_by_moderator,
    get_completed_moderation_sessions_by_moderator,
    get_moderation_session_by_id,
    set_session_moderator_photo,
    complete_moderation_session,
    update_moderator_stats_after_session,
    get_or_create_moderator_stats,
)
from keyboards.moderator_keyboards import (
    get_moderator_panel_keyboard,
    get_pending_applications_keyboard,
    get_moderation_session_keyboard,
    get_active_sessions_keyboard,
)
from handlers.states import ModeratorStates
from utils.queue import update_queue_positions, format_wait_time
from utils.user_messages import update_user_info_message, update_user_main_message
from utils.moderator_messages import get_or_create_moderator_message

logger = logging.getLogger(__name__)
router = Router()


def is_moderator(user) -> bool:
    """Проверка, является ли пользователь модератором или админом"""
    return is_moderator_or_admin(user)


@router.message(Command("moderator"))
async def cmd_moderator(message: Message, state: FSMContext):
    """Команда для доступа к панели модератора"""
    await state.clear()
    
    async for session in get_session():
        user = await get_or_create_user(
            session,
            user_id=message.from_user.id,
        )
        await session.commit()
        
        if not is_moderator(user):
            await message.answer("❌ У вас нет доступа к панели модератора")
            return
        
        await get_or_create_moderator_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text="👮 Панель модератора",
            reply_markup=get_moderator_panel_keyboard()
        )


@router.callback_query(F.data == "moderator_panel")
async def callback_moderator_panel(callback: CallbackQuery, state: FSMContext):
    """Панель модератора"""
    await state.clear()
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="👮 Панель модератора",
            reply_markup=get_moderator_panel_keyboard()
        )
        await callback.answer()


@router.callback_query(F.data == "moderator_pending_applications")
async def callback_moderator_pending_applications(callback: CallbackQuery, state: FSMContext):
    """Список ожидающих заявок"""
    await state.clear()
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        applications = await get_pending_applications(session)
        await session.commit()
        
        if not applications:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text="📋 Нет ожидающих заявок",
                reply_markup=get_moderator_panel_keyboard()
            )
        else:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=f"📋 Доступные заявки ({len(applications)}):",
                reply_markup=get_pending_applications_keyboard(applications)
            )
        await callback.answer()


@router.callback_query(F.data.startswith("moderator_take_application_"))
async def callback_moderator_take_application(callback: CallbackQuery, state: FSMContext):
    """Модератор берет заявку в работу"""
    await state.clear()
    application_id = int(callback.data.split("_")[-1])
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        application = await get_application_by_id(session, application_id)
        
        if not application:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            await session.rollback()
            return
        
        if application.status != "pending":
            await callback.answer("❌ Заявка уже обрабатывается", show_alert=True)
            await session.rollback()
            return
        
        # Назначаем модератора
        application = await assign_moderator_to_application(
            session,
            application,
            callback.from_user.id
        )
        
        # Логирование взятия заявки модератором
        logger.info(
            f"Moderator {callback.from_user.id} took application #{application_id} "
            f"from user {application.user_id}"
        )
        
        # Создаем сессию модерации
        moderation_session = await create_moderation_session(session, application)
        
        # Обновляем позиции в очереди
        await update_queue_positions(session)
        
        await session.commit()
        
        # Уведомляем пользователя через информационное сообщение
        bot = callback.bot
        try:
            # Используем application, который уже есть в памяти после commit
            wait_time_text = ""
            if application.estimated_wait_time:
                wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
            
            info_text = (
                f"📊 Статус заявки #{application.id}\n\n"
                f"✅ Модератор подключился к вашей заявке!\n"
                f"Статус: {application.status}\n\n"
                "📸 Отправьте скриншот для подтверждения возраста.\n"
                "Просто отправьте фото в этот чат."
            )
            
            if application.queue_position:
                info_text = info_text.replace(
                    f"Статус: {application.status}\n\n",
                    f"Статус: {application.status}\n📍 Позиция в очереди: {application.queue_position}{wait_time_text}\n\n"
                )
            
            await update_user_info_message(
                bot=bot,
                user_id=application.user_id,
                text=info_text
            )
        except Exception as e:
            logger.error(f"Не удалось обновить информационное сообщение пользователю {application.user_id}: {e}")
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=f"✅ Вы взяли заявку #{application_id} в работу\n\nОжидайте скриншот от пользователя.",
            reply_markup=get_moderator_panel_keyboard()
        )
        await callback.answer("Заявка взята в работу")
        
        # Устанавливаем состояние ожидания скриншота для пользователя
        from handlers.user_handlers import router as user_router
        # Это будет обработано через user_handlers


@router.callback_query(F.data == "moderator_active_sessions")
async def callback_moderator_active_sessions(callback: CallbackQuery, state: FSMContext):
    """Список активных сессий модератора"""
    await state.clear()
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        sessions = await get_active_moderation_sessions_by_moderator(
            session,
            callback.from_user.id
        )
        await session.commit()
        
        if not sessions:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text="🔄 У вас нет активных сессий",
                reply_markup=get_moderator_panel_keyboard()
            )
        else:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=f"🔄 Ваши активные сессии ({len(sessions)}):",
                reply_markup=get_active_sessions_keyboard(sessions)
            )
        await callback.answer()


@router.callback_query(F.data == "moderator_sessions_without_photo")
async def callback_moderator_sessions_without_photo(callback: CallbackQuery, state: FSMContext):
    """Список завершенных сессий без фото модератора"""
    await state.clear()
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        sessions = await get_completed_moderation_sessions_by_moderator(
            session,
            callback.from_user.id,
            limit=20
        )
        await session.commit()
        
        if not sessions:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text="✅ Все завершенные сессии имеют фото модератора",
                reply_markup=get_moderator_panel_keyboard()
            )
        else:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=f"⚠️ Завершенные сессии без фото ({len(sessions)}):\n\nВы можете открыть сессию и отправить фото пользователю.",
                reply_markup=get_active_sessions_keyboard(sessions)
            )
        await callback.answer()


@router.callback_query(F.data.startswith("moderator_session_"))
async def callback_moderator_session(callback: CallbackQuery, state: FSMContext):
    """Просмотр сессии модерации"""
    await state.clear()
    session_id = int(callback.data.split("_")[-1])
    
    async for db_session in get_session():
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        await db_session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        moderation_session = await get_moderation_session_by_id(db_session, session_id)
        await db_session.commit()
        
        if not moderation_session or moderation_session.moderator_id != callback.from_user.id:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            return
        
        # Разрешаем просмотр завершенных сессий для отправки фото
        if moderation_session.status not in ["active", "completed"]:
            await callback.answer("❌ Сессия отклонена", show_alert=True)
            return
        
        status_emoji = "🔄" if moderation_session.status == "active" else "✅"
        session_text = (
            f"{status_emoji} Сессия модерации #{session_id}\n\n"
            f"📝 Заявка: #{moderation_session.application_id}\n"
            f"👤 Пользователь: {moderation_session.user_id}\n"
            f"📊 Статус: {moderation_session.status}\n\n"
        )
        
        if moderation_session.user_photo_file_id:
            session_text += "✅ Скриншот пользователя получен\n"
        else:
            session_text += "⏳ Ожидание скриншота от пользователя\n"
        
        if moderation_session.moderator_photo_file_id:
            session_text += "✅ Фото модератора отправлено\n"
        else:
            if moderation_session.status == "completed":
                session_text += "⚠️ Фото модератора НЕ было отправлено!\n"
                session_text += "📸 Вы можете отправить фото сейчас (кнопка ниже)\n"
            else:
                session_text += "📸 Отправьте фото пользователю (нажмите кнопку ниже)"
        
        is_completed = moderation_session.status == "completed"
        keyboard = get_moderation_session_keyboard(session_id, is_completed=is_completed)
        
        # Добавляем кнопку для отправки фото, если еще не отправлено (даже для завершенных сессий)
        if not moderation_session.moderator_photo_file_id:
            from aiogram.types import InlineKeyboardButton
            keyboard.inline_keyboard.insert(0, [
                InlineKeyboardButton(
                    text="📸 Отправить фото",
                    callback_data=f"moderator_send_photo_{session_id}"
                )
            ])
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=session_text,
            reply_markup=keyboard
        )
        await callback.answer()


@router.callback_query(F.data.startswith("moderator_send_photo_"))
async def callback_moderator_send_photo(callback: CallbackQuery, state: FSMContext):
    """Модератор хочет отправить фото - переводим в состояние ожидания фото"""
    session_id = int(callback.data.split("_")[-1])
    
    async for db_session in get_session():
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        await db_session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        moderation_session = await get_moderation_session_by_id(db_session, session_id)
        await db_session.commit()
        
        if not moderation_session or moderation_session.moderator_id != callback.from_user.id:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            return
        
        # Разрешаем отправку фото даже для завершенных сессий
        if moderation_session.status not in ["active", "completed"]:
            await callback.answer("❌ Сессия отклонена", show_alert=True)
            return
        
        # Сохраняем session_id в состоянии
        await state.update_data(session_id=session_id)
        await state.set_state(ModeratorStates.waiting_for_moderator_photo)
        logger.info(f"Модератор {callback.from_user.id} переведен в состояние ожидания фото для сессии {session_id}")
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="📸 Отправьте фото для пользователя (просто отправьте фото в этот чат):",
            reply_markup=get_moderation_session_keyboard(session_id)
        )
        
        await callback.answer("Теперь отправьте фото в чат")


@router.callback_query(F.data.startswith("moderator_approve_"))
async def callback_moderator_approve(callback: CallbackQuery, state: FSMContext):
    """Модератор подтверждает заявку"""
    await state.clear()
    session_id = int(callback.data.split("_")[-1])
    logger.info(f"Модератор {callback.from_user.id} пытается подтвердить сессию {session_id}")
    
    async for db_session in get_session():
        # Проверяем права модератора
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            await db_session.rollback()
            return
        
        # Получаем сессию модерации
        moderation_session = await get_moderation_session_by_id(db_session, session_id)
        
        if not moderation_session:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            await db_session.rollback()
            return
        
        if moderation_session.moderator_id != callback.from_user.id:
            await callback.answer("❌ Это не ваша сессия", show_alert=True)
            await db_session.rollback()
            return
        
        if moderation_session.status != "active":
            await callback.answer("❌ Сессия уже завершена", show_alert=True)
            await db_session.rollback()
            return
        
        # Проверяем, было ли отправлено фото модератора
        moderator_photo_file_id = moderation_session.moderator_photo_file_id
        if not moderator_photo_file_id:
            # Предупреждаем модератора, что фото не было отправлено
            await callback.answer(
                "⚠️ Внимание: Вы не отправили фото пользователю! "
                "Рекомендуется отправить фото перед подтверждением.",
                show_alert=True
            )
            # Продолжаем выполнение - модератор может подтвердить и без фото
        
        # Сохраняем user_id и application_id до завершения сессии
        user_id = moderation_session.user_id
        application_id = moderation_session.application_id
        
        # Рассчитываем длительность сессии
        duration = int((datetime.utcnow() - moderation_session.created_at).total_seconds())
        
        # Завершаем сессию
        try:
            await complete_moderation_session(
                db_session,
                moderation_session,
                STATUS_COMPLETED
            )
        except Exception as e:
            logger.error(f"Ошибка при завершении сессии: {e}", exc_info=True)
            await callback.answer("❌ Ошибка при завершении сессии", show_alert=True)
            await db_session.rollback()
            return
        
        # Логирование подтверждения заявки
        logger.info(
            f"Moderator {callback.from_user.id} approved application "
            f"#{application_id} for user {user_id}. Session duration: {duration}s"
        )
        
        # Обновляем статистику модератора
        try:
            await update_moderator_stats_after_session(
                db_session,
                callback.from_user.id,
                duration
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}", exc_info=True)
        
        await db_session.commit()
        
        # Удаляем уведомления о заявке у всех модераторов
        from utils.moderator_messages import delete_moderator_notifications_for_application
        try:
            await delete_moderator_notifications_for_application(
                bot=callback.bot,
                application_id=application_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении уведомлений о заявке #{application_id}: {e}")
        
        # Отправляем фото модератора пользователю, если оно есть, но не было отправлено
        bot = callback.bot
        photo_sent = False
        
        if moderator_photo_file_id:
            try:
                logger.info(
                    f"Попытка отправить фото модератора пользователю {user_id} "
                    f"при подтверждении заявки #{application_id}"
                )
                sent_message = await bot.send_photo(
                    chat_id=user_id,
                    photo=moderator_photo_file_id,
                    caption=(
                        f"📸 Фото от модератора для подтверждения\n\n"
                        f"Заявка #{application_id}"
                    )
                )
                photo_sent = True
                logger.info(
                    f"✅ Фото модератора успешно отправлено пользователю {user_id} "
                    f"при подтверждении заявки #{application_id}"
                )
            except Exception as e:
                error_msg = str(e)
                logger.error(
                    f"❌ Не удалось отправить фото модератора пользователю {user_id} "
                    f"при подтверждении заявки #{application_id}: {error_msg}",
                    exc_info=True
                )
                # Продолжаем выполнение - отправляем текстовое уведомление
        
        # Уведомляем пользователя через информационное сообщение
        try:
            application = await get_application_by_id(db_session, application_id)
            await db_session.commit()
            
            if application:
                info_text = (
                    f"📊 Статус заявки #{application_id}\n\n"
                    f"✅ Ваша заявка подтверждена!\n"
                    f"Статус: {application.status}"
                )
                
                await update_user_info_message(
                    bot=bot,
                    user_id=user_id,
                    text=info_text
                )
        except Exception as e:
            logger.error(f"Не удалось обновить информационное сообщение пользователю {user_id}: {e}")
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=f"✅ Заявка #{application_id} подтверждена",
            reply_markup=get_moderator_panel_keyboard()
        )
        
        await callback.answer("Заявка подтверждена")


@router.callback_query(F.data.startswith("moderator_reject_"))
async def callback_moderator_reject(callback: CallbackQuery, state: FSMContext):
    """Модератор отклоняет заявку"""
    await state.clear()
    session_id = int(callback.data.split("_")[-1])
    logger.info(f"Модератор {callback.from_user.id} пытается отклонить сессию {session_id}")
    
    async for db_session in get_session():
        # Проверяем права модератора
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            await db_session.rollback()
            return
        
        # Получаем сессию модерации
        moderation_session = await get_moderation_session_by_id(db_session, session_id)
        
        if not moderation_session:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            await db_session.rollback()
            return
        
        if moderation_session.moderator_id != callback.from_user.id:
            await callback.answer("❌ Это не ваша сессия", show_alert=True)
            await db_session.rollback()
            return
        
        if moderation_session.status != "active":
            await callback.answer("❌ Сессия уже завершена", show_alert=True)
            await db_session.rollback()
            return
        
        # Сохраняем user_id и application_id до завершения сессии
        user_id = moderation_session.user_id
        application_id = moderation_session.application_id
        
        # Рассчитываем длительность сессии
        duration = int((datetime.utcnow() - moderation_session.created_at).total_seconds())
        
        # Завершаем сессию
        try:
            await complete_moderation_session(
                db_session,
                moderation_session,
                STATUS_REJECTED
            )
        except Exception as e:
            logger.error(f"Ошибка при завершении сессии: {e}", exc_info=True)
            await callback.answer("❌ Ошибка при завершении сессии", show_alert=True)
            await db_session.rollback()
            return
        
        # Логирование отклонения заявки
        logger.info(
            f"Moderator {callback.from_user.id} rejected application "
            f"#{application_id} for user {user_id}. Session duration: {duration}s"
        )
        
        # Обновляем статистику модератора
        try:
            await update_moderator_stats_after_session(
                db_session,
                callback.from_user.id,
                duration
            )
        except Exception as e:
            logger.error(f"Ошибка при обновлении статистики: {e}", exc_info=True)
        
        await db_session.commit()
        
        # Удаляем уведомления о заявке у всех модераторов
        from utils.moderator_messages import delete_moderator_notifications_for_application
        try:
            await delete_moderator_notifications_for_application(
                bot=callback.bot,
                application_id=application_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении уведомлений о заявке #{application_id}: {e}")
        
        # Уведомляем пользователя через информационное сообщение
        bot = callback.bot
        try:
            application = await get_application_by_id(db_session, application_id)
            await db_session.commit()
            
            if application:
                info_text = (
                    f"📊 Статус заявки #{application_id}\n\n"
                    f"❌ Ваша заявка отклонена\n"
                    f"Статус: {application.status}"
                )
                
                await update_user_info_message(
                    bot=bot,
                    user_id=user_id,
                    text=info_text
                )
        except Exception as e:
            logger.error(f"Не удалось обновить информационное сообщение пользователю {user_id}: {e}")
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=f"❌ Заявка #{application_id} отклонена",
            reply_markup=get_moderator_panel_keyboard()
        )
        
        await callback.answer("Заявка отклонена")


@router.message(ModeratorStates.waiting_for_moderator_photo, F.photo)
async def process_moderator_photo(message: Message, state: FSMContext):
    """Обработка фото от модератора"""
    logger.info(f"Получено фото от модератора {message.from_user.id}")
    photo: PhotoSize = message.photo[-1]
    file_id = photo.file_id
    
    data = await state.get_data()
    session_id = data.get("session_id")
    logger.info(f"Session ID из состояния: {session_id}")
    
    async for db_session in get_session():
        # Проверяем права модератора
        user = await get_or_create_user(db_session, user_id=message.from_user.id)
        
        if not is_moderator(user):
            await message.answer("❌ У вас нет доступа")
            await state.clear()
            await db_session.rollback()
            return
        
        # Получаем сессию модерации
        if session_id:
            moderation_session = await get_moderation_session_by_id(db_session, session_id)
        else:
            # Иначе берем первую активную сессию
            sessions = await get_active_moderation_sessions_by_moderator(
                db_session,
                message.from_user.id
            )
            if not sessions:
                await message.answer(
                    "❌ У вас нет активных сессий",
                    reply_markup=get_moderator_panel_keyboard()
                )
                await state.clear()
                await db_session.rollback()
                return
            moderation_session = sessions[0]
        
        if not moderation_session:
            await message.answer("❌ Сессия не найдена")
            await state.clear()
            await db_session.rollback()
            return
        
        if moderation_session.moderator_id != message.from_user.id:
            await message.answer("❌ Это не ваша сессия")
            await state.clear()
            await db_session.rollback()
            return
        
        # Разрешаем отправку фото даже для завершенных сессий
        if moderation_session.status not in ["active", "completed"]:
            await message.answer("❌ Сессия отклонена, нельзя отправить фото")
            await state.clear()
            await db_session.rollback()
            return
        
        # Сохраняем file_id фото
        await set_session_moderator_photo(db_session, moderation_session, file_id)
        await db_session.flush()  # Сохраняем изменения перед отправкой
        
        # Отправляем фото пользователю
        bot = message.bot
        user_id = moderation_session.user_id
        application_id = moderation_session.application_id
        
        logger.info(
            f"Попытка отправить фото от модератора {message.from_user.id} "
            f"пользователю {user_id} (Заявка #{application_id}), file_id: {file_id[:20]}..."
        )
        
        try:
            sent_message = await bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=(
                    f"📸 Фото от модератора для подтверждения\n\n"
                    f"Заявка #{application_id}"
                )
            )
            logger.info(
                f"✅ Фото от модератора {message.from_user.id} успешно отправлено пользователю "
                f"{user_id} (Заявка #{application_id}). Message ID: {sent_message.message_id}"
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f"❌ Не удалось отправить фото пользователю {user_id} (Заявка #{application_id}): {error_msg}",
                exc_info=True
            )
            
            # Более понятное сообщение об ошибке для модератора
            if "chat not found" in error_msg.lower() or "bot was blocked" in error_msg.lower():
                error_text = (
                    f"❌ Не удалось отправить фото пользователю {user_id}.\n\n"
                    f"Возможные причины:\n"
                    f"• Пользователь не начал диалог с ботом (/start)\n"
                    f"• Пользователь заблокировал бота\n\n"
                    f"Попросите пользователя написать боту /start"
                )
            else:
                error_text = (
                    f"❌ Не удалось отправить фото пользователю.\n"
                    f"Ошибка: {error_msg}"
                )
            
            is_completed = moderation_session.status == "completed"
            await message.answer(
                error_text,
                reply_markup=get_moderation_session_keyboard(moderation_session.id, is_completed=is_completed)
            )
            await db_session.rollback()
            await state.clear()
            return
        
        # Коммитим изменения только после успешной отправки
        await db_session.commit()
        
        # Обновляем информационное сообщение пользователя
        try:
            application = await get_application_by_id(db_session, application_id)
            await db_session.commit()
            
            if application:
                info_text = (
                    f"📊 Статус заявки #{application_id}\n\n"
                    f"Статус: {application.status}\n\n"
                    f"✅ Скриншот отправлен модератору\n"
                    f"📸 Фото от модератора получено"
                )
                
                if application.queue_position:
                    wait_time_text = ""
                    if application.estimated_wait_time:
                        wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
                    info_text = info_text.replace(
                        f"Статус: {application.status}\n\n",
                        f"Статус: {application.status}\n📍 Позиция в очереди: {application.queue_position}{wait_time_text}\n\n"
                    )
                
                await update_user_info_message(
                    bot=bot,
                    user_id=user_id,
                    text=info_text
                )
        except Exception as e:
            logger.error(f"Не удалось обновить информационное сообщение пользователю {user_id}: {e}")
        
        is_completed = moderation_session.status == "completed"
        await message.answer(
            f"✅ Фото отправлено пользователю (Заявка #{moderation_session.application_id})",
            reply_markup=get_moderation_session_keyboard(moderation_session.id, is_completed=is_completed)
        )
        await state.clear()


@router.message(ModeratorStates.waiting_for_moderator_photo)
async def process_moderator_photo_invalid(message: Message, state: FSMContext):
    """Обработка некорректного сообщения вместо фото"""
    # Игнорируем команды - они обрабатываются отдельными обработчиками
    # Проверяем, является ли сообщение командой через entities или начало текста
    if message.entities:
        from aiogram.enums import MessageEntityType
        for entity in message.entities:
            if entity.type == MessageEntityType.BOT_COMMAND:
                # Это команда, очищаем состояние и пропускаем
                await state.clear()
                return
    
    if message.text and message.text.startswith('/'):
        # Если это команда, очищаем состояние и пропускаем
        await state.clear()
        return
    
    await message.answer(
        "❌ Пожалуйста, отправьте фото (изображение).\n"
        "Просто отправьте фото в этот чат."
    )


@router.callback_query(F.data == "moderator_stats")
async def callback_moderator_stats(callback: CallbackQuery, state: FSMContext):
    """Статистика модератора"""
    await state.clear()
    async for db_session in get_session():
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        await db_session.commit()
        
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        
        stats = await get_or_create_moderator_stats(db_session, callback.from_user.id)
        await db_session.commit()
        
        stats_text = (
            f"📊 Ваша статистика:\n\n"
            f"📝 Всего сессий: {stats.total_sessions}\n"
            f"⏱ Среднее время сессии: {stats.average_session_time:.1f} сек\n"
            f"⏳ Общее время: {stats.total_time_seconds} сек"
        )
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=stats_text,
            reply_markup=get_moderator_panel_keyboard()
        )
        await callback.answer()
