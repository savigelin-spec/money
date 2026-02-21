"""
Обработчики для модераторов
"""
import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext

from config import ROLE_MODERATOR, ROLE_ADMIN, STATUS_COMPLETED, STATUS_REJECTED, STATUS_CANCELLED
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
    complete_moderation_session,
    end_session_chat_only,
    add_session_message,
    update_moderator_stats_after_session,
    get_or_create_moderator_stats,
)
from keyboards.moderator_keyboards import (
    get_moderator_panel_keyboard,
    get_pending_applications_keyboard,
    get_moderation_session_keyboard,
    get_active_sessions_keyboard,
)
from keyboards.user_keyboards import get_dismiss_notification_keyboard
from utils.queue import update_queue_positions, format_wait_time
from utils.user_messages import update_user_info_message, update_user_main_message
from utils.moderator_messages import get_or_create_moderator_message

logger = logging.getLogger(__name__)
router = Router()


def is_moderator(user) -> bool:
    """Проверка, является ли пользователь модератором или админом"""
    return is_moderator_or_admin(user)


class IsModeratorMessageFilter(Filter):
    """Фильтр: только сообщения от модератора. Иначе апдейт уходит в следующий роутер (user_handlers)."""

    async def __call__(self, message: Message) -> bool:
        async for db_session in get_session():
            user = await get_or_create_user(db_session, user_id=message.from_user.id)
            await db_session.commit()
            return is_moderator(user)
        return False


def _user_inactive_minutes(moderation_session) -> float | None:
    """Минут с последней активности пользователя. None если сессия не активна или нет данных."""
    if moderation_session.status != "active":
        return None
    t = moderation_session.last_user_activity_at or moderation_session.created_at
    return (datetime.utcnow() - t).total_seconds() / 60.0


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
                "Можете писать сообщения и отправлять фото в этот чат — они сразу уйдут модератору."
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
            "Лайв-чат: пишите сообщения и отправляйте фото — они уйдут пользователю."
        )
        is_completed = moderation_session.status == "completed"
        user_inactive = _user_inactive_minutes(moderation_session)
        keyboard = get_moderation_session_keyboard(
            session_id, is_completed=is_completed, user_inactive_minutes=user_inactive
        )
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=session_text,
            reply_markup=keyboard
        )
        await callback.answer()


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
            await callback.answer("Сессия уже завершена", show_alert=True)
            await update_user_main_message(
                callback.bot,
                callback.from_user.id,
                text="👮 Панель модератора",
                reply_markup=get_moderator_panel_keyboard(),
            )
            await db_session.rollback()
            return
        
        # Сохраняем user_id и application_id до завершения сессии
        user_id = moderation_session.user_id
        application_id = moderation_session.application_id
        
        # Сохраняем message_id для удаления до завершения сессии
        moderator_screenshot_msg_id = moderation_session.moderator_screenshot_message_id
        moderator_own_photo_msg_id = moderation_session.moderator_own_photo_message_id
        moderator_id = moderation_session.moderator_id
        
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
        
        # Единая очистка сообщений сессии (лайв-чат, инфо, скриншот, фото) до commit
        try:
            from utils.session_cleanup import delete_all_session_messages
            await delete_all_session_messages(
                callback.bot,
                db_session,
                session_id,
            )
        except Exception as e:
            logger.error(f"Ошибка при очистке сообщений сессии #{session_id}: {e}", exc_info=True)

        await db_session.commit()

        # Оповещение о заявке («Новая заявка #N») не удаляем — остаётся в чате модератора

        bot = callback.bot
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
        
        try:
            await bot.send_message(
                user_id,
                "Сессия завершена модератором. Ваша заявка подтверждена.",
                reply_markup=get_dismiss_notification_keyboard(),
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
        
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
            await callback.answer("Сессия уже завершена", show_alert=True)
            await update_user_main_message(
                callback.bot,
                callback.from_user.id,
                text="👮 Панель модератора",
                reply_markup=get_moderator_panel_keyboard(),
            )
            await db_session.rollback()
            return
        
        # Сохраняем user_id и application_id до завершения сессии
        user_id = moderation_session.user_id
        application_id = moderation_session.application_id
        
        # Сохраняем message_id для удаления до завершения сессии
        moderator_screenshot_msg_id = moderation_session.moderator_screenshot_message_id
        moderator_own_photo_msg_id = moderation_session.moderator_own_photo_message_id
        moderator_id = moderation_session.moderator_id
        
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
        
        # Единая очистка сообщений сессии до commit
        try:
            from utils.session_cleanup import delete_all_session_messages
            await delete_all_session_messages(
                callback.bot,
                db_session,
                session_id,
            )
        except Exception as e:
            logger.error(f"Ошибка при очистке сообщений сессии #{session_id}: {e}", exc_info=True)

        await db_session.commit()

        # Оповещение о заявке («Новая заявка #N») не удаляем — остаётся в чате модератора

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
        
        try:
            await bot.send_message(
                user_id,
                "Сессия завершена модератором. Ваша заявка отклонена.",
                reply_markup=get_dismiss_notification_keyboard(),
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=f"❌ Заявка #{application_id} отклонена",
            reply_markup=get_moderator_panel_keyboard()
        )
        
        await callback.answer("Заявка отклонена")


@router.callback_query(F.data.startswith("moderator_end_request_"))
async def callback_moderator_end_request(callback: CallbackQuery, state: FSMContext):
    """Одна кнопка «Завершить заявку»: при < 3 мин — alert, при >= 3 мин — завершение сессии."""
    await state.clear()
    session_id = int(callback.data.split("_")[-1])
    user_id_to_notify = None
    async for db_session in get_session():
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        moderation_session = await get_moderation_session_by_id(db_session, session_id)
        if not moderation_session or moderation_session.moderator_id != callback.from_user.id:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            return
        if moderation_session.status != "active":
            await callback.answer("Сессия уже завершена", show_alert=True)
            await update_user_main_message(
                callback.bot,
                callback.from_user.id,
                text="👮 Панель модератора",
                reply_markup=get_moderator_panel_keyboard(),
            )
            return
        inactive_min = _user_inactive_minutes(moderation_session)
        if inactive_min is None or inactive_min < 3:
            await callback.answer(
                "Подождите 3 минуты с последнего сообщения пользователя.",
                show_alert=True,
            )
            return
        user_id_to_notify = moderation_session.user_id
        try:
            await end_session_chat_only(db_session, moderation_session)
        except Exception as e:
            logger.error(f"Ошибка при завершении заявки: {e}", exc_info=True)
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        application = await get_application_by_id(db_session, moderation_session.application_id)
        if application:
            application.status = STATUS_CANCELLED
        try:
            from utils.session_cleanup import delete_all_session_messages
            await delete_all_session_messages(callback.bot, db_session, session_id)
        except Exception as e:
            logger.error(f"Ошибка при очистке сообщений сессии #{session_id}: {e}", exc_info=True)
        await db_session.commit()
        break
    else:
        user_id_to_notify = None
    await update_user_main_message(
        callback.bot,
        callback.from_user.id,
        text="Заявка завершена.",
        reply_markup=get_moderator_panel_keyboard(),
    )
    if user_id_to_notify is not None:
        try:
            await callback.bot.send_message(
                user_id_to_notify,
                "Сессия завершена модератором.",
                reply_markup=get_dismiss_notification_keyboard(),
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {user_id_to_notify}: {e}")
    await callback.answer("Заявка завершена")


@router.callback_query(F.data.startswith("moderator_end_session_inactive_"))
async def callback_moderator_end_session_inactive(callback: CallbackQuery, state: FSMContext):
    """Модератор завершает сессию по неактивности (≥ 3 мин). Оставлен для совместимости со старыми сообщениями."""
    await state.clear()
    session_id = int(callback.data.split("_")[-1])
    user_id_to_notify = None
    async for db_session in get_session():
        user = await get_or_create_user(db_session, user_id=callback.from_user.id)
        if not is_moderator(user):
            await callback.answer("❌ Нет доступа", show_alert=True)
            return
        moderation_session = await get_moderation_session_by_id(db_session, session_id)
        if not moderation_session or moderation_session.moderator_id != callback.from_user.id:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            return
        if moderation_session.status != "active":
            await callback.answer("Сессия уже завершена", show_alert=True)
            await update_user_main_message(
                callback.bot,
                callback.from_user.id,
                text="👮 Панель модератора",
                reply_markup=get_moderator_panel_keyboard(),
            )
            return
        inactive_min = _user_inactive_minutes(moderation_session)
        if inactive_min is None or inactive_min < 3:
            await callback.answer("❌ Завершить можно только при неактивности пользователя от 3 минут", show_alert=True)
            return
        user_id_to_notify = moderation_session.user_id
        try:
            await end_session_chat_only(db_session, moderation_session)
        except Exception as e:
            logger.error(f"Ошибка при завершении сессии по неактивности: {e}", exc_info=True)
            await callback.answer("❌ Ошибка", show_alert=True)
            return
        application = await get_application_by_id(db_session, moderation_session.application_id)
        if application:
            application.status = STATUS_CANCELLED
        try:
            from utils.session_cleanup import delete_all_session_messages
            await delete_all_session_messages(callback.bot, db_session, session_id)
        except Exception as e:
            logger.error(f"Ошибка при очистке сообщений сессии #{session_id}: {e}", exc_info=True)
        await db_session.commit()
        break
    else:
        user_id_to_notify = None
    await update_user_main_message(
        callback.bot,
        callback.from_user.id,
        text=f"Сессия #{session_id} завершена по неактивности пользователя.",
        reply_markup=get_moderator_panel_keyboard(),
    )
    if user_id_to_notify is not None:
        try:
            await callback.bot.send_message(
                user_id_to_notify,
                "Сессия завершена модератором.",
                reply_markup=get_dismiss_notification_keyboard(),
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {user_id_to_notify}: {e}")
    await callback.answer("Сессия завершена по неактивности")


@router.message(F.photo, IsModeratorMessageFilter())
async def process_moderator_live_chat_photo(message: Message, state: FSMContext):
    """Лайв-чат: пересылка фото от модератора пользователю при одной активной сессии."""
    await state.clear()
    photo = message.photo[-1]
    file_id = photo.file_id
    async for db_session in get_session():
        sessions = await get_active_moderation_sessions_by_moderator(db_session, message.from_user.id)
        if len(sessions) != 1:
            await update_user_main_message(
                message.bot,
                message.from_user.id,
                text="👮 Панель модератора\n\nℹ️ Нет активной сессии (чат мог быть завершён пользователем).",
                reply_markup=get_moderator_panel_keyboard(),
            )
            return
        mod_session = sessions[0]
        try:
            sent = await message.bot.send_photo(
                chat_id=mod_session.user_id,
                photo=file_id,
                caption=f"👮 Модератор (заявка #{mod_session.application_id}): [фото]",
            )
            await add_session_message(db_session, mod_session.id, mod_session.user_id, sent.message_id)
            await add_session_message(db_session, mod_session.id, message.from_user.id, message.message_id)
            await db_session.commit()
        except Exception as e:
            logger.error(f"Лайв-чат: ошибка пересылки фото пользователю: {e}")
        return


@router.message(F.text, IsModeratorMessageFilter())
async def process_moderator_live_chat_text(message: Message, state: FSMContext):
    """Лайв-чат: пересылка текста от модератора пользователю при одной активной сессии. Только для модераторов (фильтр)."""
    await state.clear()
    if not message.text or message.text.strip().startswith("/"):
        return
    async for db_session in get_session():
        sessions = await get_active_moderation_sessions_by_moderator(db_session, message.from_user.id)
        if len(sessions) != 1:
            await update_user_main_message(
                message.bot,
                message.from_user.id,
                text="👮 Панель модератора\n\nℹ️ Нет активной сессии (чат мог быть завершён пользователем).",
                reply_markup=get_moderator_panel_keyboard(),
            )
            return
        mod_session = sessions[0]
        try:
            sent = await message.bot.send_message(
                chat_id=mod_session.user_id,
                text=f"👮 Модератор (заявка #{mod_session.application_id}):\n\n{message.text}",
            )
            await add_session_message(db_session, mod_session.id, mod_session.user_id, sent.message_id)
            await add_session_message(db_session, mod_session.id, message.from_user.id, message.message_id)
            await db_session.commit()
        except Exception as e:
            logger.error(f"Лайв-чат: ошибка пересылки текста пользователю: {e}")
        return


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
