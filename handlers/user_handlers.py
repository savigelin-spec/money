"""
Обработчики для пользователей
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from config import APPLICATION_COST, ROLE_MODERATOR, ROLE_ADMIN
from utils.security import is_moderator_or_admin
from database.db import get_session
from database.queries import (
    get_or_create_user,
    can_create_application,
    create_application,
    get_user_applications,
    get_application_by_id,
    get_active_moderation_session_by_user,
    set_session_user_photo,
    get_all_moderators,
)
from keyboards.user_keyboards import (
    get_main_menu_keyboard,
    get_back_to_menu_keyboard,
    get_application_status_keyboard,
    get_applications_list_keyboard,
)
from handlers.states import UserStates, ModeratorStates
from utils.queue import update_queue_positions, format_wait_time
from utils.balance import test_deposit
from utils.user_messages import (
    get_or_create_user_main_message,
    get_or_create_user_info_message,
    update_user_info_message,
    update_user_main_message,
)
from datetime import datetime

logger = logging.getLogger(__name__)
router = Router()


async def notify_moderators_new_application(bot, application):
    """Отправить уведомление всем модераторам о новой заявке"""
    async for session in get_session():
        moderators = await get_all_moderators(session)
        await session.commit()
        
        if not moderators:
            logger.info("Нет модераторов для уведомления")
            return
        
        notification_text = (
            f"🔔 Новая заявка #{application.id}\n\n"
            f"👤 Пользователь: {application.user_id}\n"
            f"📊 Позиция в очереди: {application.queue_position or 'рассчитывается...'}\n"
            f"📅 Создана: {application.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        
        from keyboards.moderator_keyboards import get_moderator_panel_keyboard
        
        for moderator in moderators:
            try:
                await bot.send_message(
                    chat_id=moderator.user_id,
                    text=notification_text,
                    reply_markup=get_moderator_panel_keyboard()
                )
                logger.info(f"Уведомление о заявке #{application.id} отправлено модератору {moderator.user_id}")
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление модератору {moderator.user_id}: {e}")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    
    async for session in get_session():
        user = await get_or_create_user(
            session,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        await session.commit()
    
    welcome_text = (
        "👋 Добро пожаловать в бот для подтверждения возраста КСО!\n\n"
        "Выберите действие:"
    )
    
    # Проверяем, является ли пользователь модератором
    async for session in get_session():
        user = await get_or_create_user(
            session,
            user_id=message.from_user.id,
        )
        is_moderator_user = is_moderator_or_admin(user)
        await session.commit()
    
    # Создаем или обновляем главное сообщение с меню
    await get_or_create_user_main_message(
        bot=message.bot,
        user_id=message.from_user.id,
        text=welcome_text,
        reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user)
    )
    
    # Проверяем, есть ли активная сессия для информационного сообщения
    async for session in get_session():
        moderation_session = await get_active_moderation_session_by_user(
            session,
            message.from_user.id
        )
        await session.commit()
        
        if moderation_session:
            # Формируем текст информационного сообщения
            application = await get_application_by_id(session, moderation_session.application_id)
            await session.commit()
            
            if application:
                wait_time_text = ""
                if application.estimated_wait_time:
                    wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
                
                info_text = (
                    f"📊 Статус заявки #{application.id}\n\n"
                    f"Статус: {application.status}"
                )
                
                if application.queue_position:
                    info_text += f"\n📍 Позиция в очереди: {application.queue_position}{wait_time_text}"
                
                if moderation_session.user_photo_file_id:
                    info_text += "\n\n✅ Скриншот отправлен модератору. Ожидайте ответа."
                
                # Создаем или обновляем информационное сообщение
                await get_or_create_user_info_message(
                    bot=message.bot,
                    user_id=message.from_user.id,
                    text=info_text
                )


@router.callback_query(F.data == "go_to_moderator_panel")
async def callback_go_to_moderator_panel(callback: CallbackQuery, state: FSMContext):
    """Переход в панель модератора из главного меню"""
    await state.clear()
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
        if not is_moderator_or_admin(user):
            await callback.answer("❌ У вас нет доступа к панели модератора", show_alert=True)
            return
    
    # Отправляем панель модератора
    from keyboards.moderator_keyboards import get_moderator_panel_keyboard
    
    await callback.message.answer(
        "👮 Панель модератора",
        reply_markup=get_moderator_panel_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    
    # Проверяем, является ли пользователь модератором
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        is_moderator_user = is_moderator_or_admin(user)
        await session.commit()
    
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="Главное меню:",
        reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user)
    )
    await callback.answer()


@router.callback_query(F.data == "create_application")
async def callback_create_application(callback: CallbackQuery, state: FSMContext):
    """Создание заявки на подтверждение"""
    async for session in get_session():
        user = await get_or_create_user(
            session,
            user_id=callback.from_user.id,
        )
        
        if not await can_create_application(session, user):
            if user.balance < APPLICATION_COST:
                await callback.answer(
                    f"❌ Недостаточно средств! Ваш баланс: {user.balance}⭐. "
                    f"Необходимо: {APPLICATION_COST}⭐",
                    show_alert=True
                )
            else:
                await callback.answer(
                    "❌ У вас уже есть активная заявка!",
                    show_alert=True
                )
            await session.rollback()
            return
        
        # Создаем заявку
        application = await create_application(session, user)
        
        # Логирование создания заявки
        logger.info(
            f"User {callback.from_user.id} created application #{application.id}. "
            f"Balance after: {user.balance}⭐"
        )
        
        # Обновляем позиции в очереди
        await update_queue_positions(session)
        
        # Получаем обновленную заявку с позицией
        await session.refresh(application)
        
        await session.commit()
        
        # Создаем сессию модерации (если еще не создана)
        moderation_session = await get_active_moderation_session_by_user(session, callback.from_user.id)
        if not moderation_session:
            # Сессия будет создана модератором при взятии заявки
            pass
        
        await session.commit()
        
        wait_time_text = ""
        if application.estimated_wait_time:
            wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
        
        info_text = (
            f"📊 Статус заявки #{application.id}\n\n"
            f"✅ Заявка создана!\n"
            f"📊 Позиция в очереди: {application.queue_position or 'рассчитывается...'}{wait_time_text}\n\n"
            "Ожидайте подключения модератора. Вы получите уведомление, когда модератор начнет работу с вашей заявкой."
        )
        
        # Проверяем, является ли пользователь модератором
        is_moderator_user = is_moderator_or_admin(user)
        
        # Обновляем главное сообщение обратно в меню
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="Главное меню:",
            reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user)
        )
        
        # Отправляем уведомления модераторам о новой заявке
        await notify_moderators_new_application(callback.bot, application)
        
        # Обновляем информационное сообщение (если сессия уже есть) или создаем новое
        # Но сессии еще нет, так что просто обновим главное сообщение с информацией
        # Информационное сообщение будет создано, когда модератор возьмет заявку
        await callback.answer("Заявка создана!")
        return


@router.callback_query(F.data == "show_balance")
async def callback_show_balance(callback: CallbackQuery):
    """Показать баланс пользователя"""
    async for session in get_session():
        user = await get_or_create_user(
            session,
            user_id=callback.from_user.id,
        )
        await session.commit()
        
        balance_text = (
            f"💰 Ваш баланс: {user.balance}⭐\n\n"
            f"Стоимость заявки: {APPLICATION_COST}⭐"
        )
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=balance_text,
            reply_markup=get_back_to_menu_keyboard()
        )
        await callback.answer()


@router.callback_query(F.data == "deposit_balance")
async def callback_deposit_balance(callback: CallbackQuery, state: FSMContext):
    """Начать процесс пополнения баланса через Telegram Stars"""
    await state.clear()
    
    # Предлагаем стандартные суммы или ввод своей
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="100⭐", callback_data="deposit_amount_100"),
            InlineKeyboardButton(text="500⭐", callback_data="deposit_amount_500"),
        ],
        [
            InlineKeyboardButton(text="1000⭐", callback_data="deposit_amount_1000"),
            InlineKeyboardButton(text="2000⭐", callback_data="deposit_amount_2000"),
        ],
        [
            InlineKeyboardButton(text="💵 Другая сумма", callback_data="deposit_custom_amount"),
        ],
        [
            InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu"),
        ]
    ])
    
    deposit_text = (
        "💳 Пополнение баланса через Telegram Stars\n\n"
        "Выберите сумму пополнения или укажите свою:"
    )
    
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text=deposit_text,
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deposit_amount_"))
async def callback_deposit_amount(callback: CallbackQuery):
    """Обработка выбора суммы пополнения"""
    try:
        amount = int(callback.data.split("_")[-1])
        await create_stars_invoice(callback, amount)
    except ValueError:
        await callback.answer("❌ Ошибка: неверная сумма", show_alert=True)


@router.callback_query(F.data == "deposit_custom_amount")
async def callback_deposit_custom_amount(callback: CallbackQuery, state: FSMContext):
    """Запрос пользовательской суммы пополнения"""
    await state.set_state(UserStates.waiting_for_payment_amount)
    
    deposit_text = (
        "💳 Пополнение баланса\n\n"
        "Введите количество звёзд для пополнения (минимум 1⭐):"
    )
    
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text=deposit_text,
        reply_markup=get_back_to_menu_keyboard()
    )
    await callback.answer()


@router.message(UserStates.waiting_for_payment_amount, F.text.regexp(r'^\d+$'))
async def process_payment_amount(message: Message, state: FSMContext):
    """Обработка пользовательской суммы пополнения"""
    try:
        amount = int(message.text)
        if amount <= 0:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text="❌ Количество звёзд должно быть положительным числом",
                reply_markup=get_back_to_menu_keyboard()
            )
            return
        
        if amount < 1:
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text="❌ Минимальная сумма пополнения: 1⭐",
                reply_markup=get_back_to_menu_keyboard()
            )
            return

        # Создаём инвойс для оплаты
        await create_stars_invoice_message(message, amount)
        await state.clear()

    except ValueError:
        await update_user_main_message(
            bot=message.bot,
            user_id=message.from_user.id,
            text="❌ Неверный формат. Введите целое число (например: 500 или 1000)",
            reply_markup=get_back_to_menu_keyboard()
        )


@router.message(UserStates.waiting_for_payment_amount)
async def process_payment_amount_invalid(message: Message):
    """Обработка неверного формата суммы"""
    await update_user_main_message(
        bot=message.bot,
        user_id=message.from_user.id,
        text="❌ Пожалуйста, введите целое число (например: 500)",
        reply_markup=get_back_to_menu_keyboard()
    )


async def create_stars_invoice(callback_or_message, amount: int):
    """Создать инвойс для оплаты через Telegram Stars"""
    from aiogram.types import LabeledPrice
    
    user_id = callback_or_message.from_user.id
    timestamp = int(datetime.utcnow().timestamp())
    payload = f"deposit_{user_id}_{amount}_{timestamp}"
    
    title = f"Пополнение баланса на {amount}⭐"
    description = f"Пополнение баланса в боте на {amount} Telegram Stars"
    
    # Для Telegram Stars используем currency='XTR'
    # Сумма указывается напрямую в Stars (не в центах!)
    # provider_token должен быть опущен (не пустая строка!)
    prices = [LabeledPrice(label=f"{amount} Stars", amount=amount)]
    
    try:
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.answer_invoice(
                title=title,
                description=description,
                payload=payload,
                currency="XTR",  # Telegram Stars
                prices=prices,
                # provider_token не указываем для Stars!
            )
            await callback_or_message.answer()
        else:
            await callback_or_message.answer_invoice(
                title=title,
                description=description,
                payload=payload,
                currency="XTR",  # Telegram Stars
                prices=prices,
                # provider_token не указываем для Stars!
            )
        
        logger.info(f"Создан инвойс для пользователя {user_id}: {amount}⭐")
        
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса: {e}", exc_info=True)
        error_text = (
            "❌ Не удалось создать счёт для оплаты.\n"
            "Пожалуйста, попробуйте позже или свяжитесь с администратором."
        )
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.message.answer(error_text, reply_markup=get_back_to_menu_keyboard())
            await callback_or_message.answer("Ошибка", show_alert=True)
        else:
            await callback_or_message.answer(error_text, reply_markup=get_back_to_menu_keyboard())


async def create_stars_invoice_message(message: Message, amount: int):
    """Создать инвойс для оплаты через Telegram Stars (для message)"""
    await create_stars_invoice(message, amount)


@router.callback_query(F.data == "my_applications")
async def callback_my_applications(callback: CallbackQuery):
    """Показать список заявок пользователя"""
    async for session in get_session():
        applications = await get_user_applications(session, callback.from_user.id)
        await session.commit()
        
        if not applications:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text="📋 У вас пока нет заявок.\n\nСоздайте первую заявку через главное меню.",
                reply_markup=get_back_to_menu_keyboard()
            )
        else:
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=f"📋 Ваши заявки ({len(applications)}):",
                reply_markup=get_applications_list_keyboard(applications)
            )
        await callback.answer()


@router.callback_query(F.data.startswith("view_application_"))
async def callback_view_application(callback: CallbackQuery):
    """Просмотр конкретной заявки"""
    application_id = int(callback.data.split("_")[-1])
    
    async for session in get_session():
        application = await get_application_by_id(session, application_id)
        await session.commit()
        
        if not application or application.user_id != callback.from_user.id:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        status_emoji = {
            "pending": "⏳",
            "moderating": "🔄",
            "completed": "✅",
            "rejected": "❌"
        }.get(application.status, "❓")
        
        wait_time_text = ""
        if application.estimated_wait_time and application.status == "pending":
            wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
        
        app_text = (
            f"{status_emoji} Заявка #{application.id}\n\n"
            f"📊 Статус: {application.status}\n"
            f"📅 Создана: {application.created_at.strftime('%d.%m.%Y %H:%M')}"
        )
        
        if application.queue_position:
            app_text += f"\n📍 Позиция в очереди: {application.queue_position}{wait_time_text}"
        
        if application.started_at:
            app_text += f"\n🔄 Начата: {application.started_at.strftime('%d.%m.%Y %H:%M')}"
        
        if application.completed_at:
            app_text += f"\n✅ Завершена: {application.completed_at.strftime('%d.%m.%Y %H:%M')}"
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=app_text,
            reply_markup=get_application_status_keyboard(application_id)
        )
        await callback.answer()


@router.callback_query(F.data.startswith("refresh_application_"))
async def callback_refresh_application(callback: CallbackQuery):
    """Обновить статус заявки"""
    application_id = int(callback.data.split("_")[-1])
    
    async for session in get_session():
        application = await get_application_by_id(session, application_id)
        
        if application and application.status == "pending":
            await update_queue_positions(session)
            await session.refresh(application)
        
        await session.commit()
        
        if not application or application.user_id != callback.from_user.id:
            await callback.answer("❌ Заявка не найдена", show_alert=True)
            return
        
        await callback.answer("✅ Статус обновлен")
        # Переходим к просмотру заявки с обработкой ошибки
        try:
            await callback_view_application(callback)
        except Exception as e:
            # Если сообщение не изменилось, просто игнорируем ошибку
            if "message is not modified" not in str(e):
                logger.error(f"Ошибка при обновлении заявки: {e}")
                await callback.answer("❌ Ошибка обновления", show_alert=True)


@router.message(F.photo)
async def process_user_screenshot(message: Message, state: FSMContext):
    """Обработка скриншота от пользователя (может быть отправлен в любой момент при активной сессии)"""
    # Проверяем, не является ли это фото от модератора (модератор в состоянии ожидания фото)
    current_state = await state.get_state()
    if current_state and str(current_state) == str(ModeratorStates.waiting_for_moderator_photo):
        # Это фото от модератора, пропускаем его обработчику модератора
        logger.debug(f"Пропускаем фото от модератора {message.from_user.id} в состоянии {current_state}")
        return
    
    photo: PhotoSize = message.photo[-1]  # Берем фото наибольшего размера
    file_id = photo.file_id
    photo_message_id = message.message_id  # Сохраняем ID сообщения со скриншотом для удаления
    
    async for session in get_session():
        session_obj = await get_active_moderation_session_by_user(
            session,
            message.from_user.id
        )
        
        if not session_obj:
            # Если нет активной сессии, просто игнорируем фото
            return
        
        # Сохраняем file_id скриншота
        await set_session_user_photo(session, session_obj, file_id)
        
        # Отправляем скриншот модератору
        bot = message.bot
        
        try:
            await bot.send_photo(
                chat_id=session_obj.moderator_id,
                photo=file_id,
                caption=f"📸 Скриншот от пользователя (Заявка #{session_obj.application_id})"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить скриншот модератору: {e}")
            await session.rollback()
            return
        
        await session.commit()
        
        # Пытаемся удалить сообщение со скриншотом
        # ВАЖНО: В личном чате бот НЕ МОЖЕТ удалять сообщения пользователя!
        # Это ограничение Telegram Bot API. Бот может удалять только свои сообщения.
        from utils.user_messages import delete_user_photo_message
        
        # Пытаемся удалить сообщение пользователя (может не сработать в личном чате)
        logger.info(f"Попытка удалить сообщение {photo_message_id} от пользователя {message.from_user.id} в чате {message.chat.id}")
        deleted = await delete_user_photo_message(
            bot=bot,
            chat_id=message.chat.id,
            message_id=photo_message_id
        )
        
        if not deleted:
            logger.warning(
                f"Не удалось удалить сообщение пользователя {photo_message_id}. "
                f"Это нормально для личных чатов - бот не может удалять сообщения пользователя. "
                f"Сообщение останется в чате, но информационное сообщение будет обновлено."
            )
        
        # Обновляем информационное сообщение
        application = await get_application_by_id(session, session_obj.application_id)
        await session.commit()
        
        if application:
            wait_time_text = ""
            if application.estimated_wait_time:
                wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
            
            info_text = (
                f"📊 Статус заявки #{application.id}\n\n"
                f"Статус: {application.status}"
            )
            
            if application.queue_position:
                info_text += f"\n📍 Позиция в очереди: {application.queue_position}{wait_time_text}"
            
            info_text += "\n\n✅ Скриншот отправлен модератору. Ожидайте ответа."
            
            # Обновляем информационное сообщение
            await update_user_info_message(
                bot=bot,
                user_id=message.from_user.id,
                text=info_text
            )
        
        await state.clear()


@router.message(UserStates.waiting_for_screenshot)
async def process_user_screenshot_invalid(message: Message):
    """Обработка некорректного сообщения вместо скриншота"""
    # Обновляем информационное сообщение, если есть активная сессия
    async for session in get_session():
        moderation_session = await get_active_moderation_session_by_user(
            session,
            message.from_user.id
        )
        await session.commit()
        
        if moderation_session:
            await update_user_info_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text="❌ Пожалуйста, отправьте скриншот (фото)"
            )
        else:
            # Если нет активной сессии, обновляем главное сообщение
            await update_user_main_message(
                bot=message.bot,
                user_id=message.from_user.id,
                text="❌ Пожалуйста, отправьте скриншот (фото)",
                reply_markup=get_back_to_menu_keyboard()
            )
