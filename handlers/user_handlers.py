"""
Обработчики для пользователей
"""
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, PhotoSize
from aiogram.filters import Command, or_f
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest

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
    set_user_main_message_id,
    get_all_moderators,
    get_moderation_session_by_id,
    get_user_queue_count,
    get_user_completed_count,
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
    get_main_menu_text,
)
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = Router()

# Отдельный роутер для команды /start - должен обрабатываться ПЕРВЫМ
start_router = Router()


# ВАЖНО: Обработчик команды /start должен быть зарегистрирован ПЕРВЫМ,
# чтобы он обрабатывался независимо от состояния FSM
@start_router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.clear()
    main_menu_text = ""
    is_moderator_user = False
    is_admin_user = False

    async for session in get_session():
        user = await get_or_create_user(
            session,
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
        is_moderator_user = is_moderator_or_admin(user)
        is_admin_user = user.role == ROLE_ADMIN

        queue_count = await get_user_queue_count(session, message.from_user.id)
        now = datetime.utcnow()
        start_today = datetime(now.year, now.month, now.day)
        completed_today = await get_user_completed_count(
            session, message.from_user.id, start_today, now
        )
        completed_week = await get_user_completed_count(
            session, message.from_user.id, now - timedelta(days=7), now
        )
        completed_month = await get_user_completed_count(
            session, message.from_user.id, now - timedelta(days=30), now
        )
        completed_total = await get_user_completed_count(
            session, message.from_user.id, None, None
        )
        main_menu_text = get_main_menu_text(
            user.first_name,
            user.balance,
            queue_count,
            completed_today,
            completed_week,
            completed_month,
            completed_total,
        )
        await session.commit()
        break

    # Создаем или обновляем главное сообщение с меню
    main_msg_id = await get_or_create_user_main_message(
        bot=message.bot,
        user_id=message.from_user.id,
        text=main_menu_text,
        reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user, is_admin=is_admin_user)
    )
    # Если не удалось создать/обновить главное сообщение (например, первый запрос к БД),
    # отправляем ответ в чат и сохраняем message_id, чтобы меню работало со второго раза
    if main_msg_id is None:
        sent = await message.answer(
            main_menu_text,
            reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user, is_admin=is_admin_user)
        )
        async for session in get_session():
            await set_user_main_message_id(session, message.from_user.id, sent.message_id)
            await session.commit()
            break

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


async def notify_moderators_new_application(bot, application):
    """Отправить уведомление всем модераторам о новой заявке"""
    from database.queries import save_moderator_notification
    
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
        
        for moderator in moderators:
            try:
                sent_message = await bot.send_message(
                    chat_id=moderator.user_id,
                    text=notification_text
                )
                
                # Сохраняем message_id уведомления в БД
                async for session in get_session():
                    await save_moderator_notification(
                        session,
                        moderator_id=moderator.user_id,
                        application_id=application.id,
                        message_id=sent_message.message_id
                    )
                    await session.commit()
                
                logger.info(
                    f"Уведомление о заявке #{application.id} отправлено модератору "
                    f"{moderator.user_id}, message_id={sent_message.message_id}"
                )
            except Exception as e:
                logger.error(f"Не удалось отправить уведомление модератору {moderator.user_id}: {e}")


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
    
    # Обновляем главное сообщение панелью модератора
    from keyboards.moderator_keyboards import get_moderator_panel_keyboard
    
    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text="👮 Панель модератора",
        reply_markup=get_moderator_panel_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    main_menu_text = ""
    is_moderator_user = False
    is_admin_user = False

    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        is_moderator_user = is_moderator_or_admin(user)
        is_admin_user = user.role == ROLE_ADMIN

        queue_count = await get_user_queue_count(session, callback.from_user.id)
        now = datetime.utcnow()
        start_today = datetime(now.year, now.month, now.day)
        completed_today = await get_user_completed_count(
            session, callback.from_user.id, start_today, now
        )
        completed_week = await get_user_completed_count(
            session, callback.from_user.id, now - timedelta(days=7), now
        )
        completed_month = await get_user_completed_count(
            session, callback.from_user.id, now - timedelta(days=30), now
        )
        completed_total = await get_user_completed_count(
            session, callback.from_user.id, None, None
        )
        main_menu_text = get_main_menu_text(
            user.first_name,
            user.balance,
            queue_count,
            completed_today,
            completed_week,
            completed_month,
            completed_total,
        )

        if user.invoice_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.from_user.id,
                    message_id=user.invoice_message_id
                )
                logger.info(f"Удалён инвойс (message_id={user.invoice_message_id}) при возврате в главное меню")
                user.invoice_message_id = None
            except Exception as e:
                logger.debug(f"Не удалось удалить инвойс (message_id={user.invoice_message_id}): {e}")
                user.invoice_message_id = None

        await session.commit()
        break

    await update_user_main_message(
        bot=callback.bot,
        user_id=callback.from_user.id,
        text=main_menu_text,
        reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user, is_admin=is_admin_user)
    )
    await callback.answer()


@router.callback_query(F.data == "create_application")
async def callback_create_application(callback: CallbackQuery, state: FSMContext):
    """Показать экран подтверждения создания заявки"""
    await state.clear()
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        
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
            return
        
        # Показываем экран подтверждения
        confirmation_text = (
            f"📋 Подтверждение создания заявки\n\n"
            f"💰 Стоимость: {APPLICATION_COST}⭐\n"
            f"💵 Ваш баланс: {user.balance}⭐\n"
            f"💵 Баланс после списания: {user.balance - APPLICATION_COST}⭐\n\n"
            f"После создания заявки средства будут списаны с вашего баланса."
        )
        
        from keyboards.user_keyboards import get_application_confirmation_keyboard
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=confirmation_text,
            reply_markup=get_application_confirmation_keyboard()
        )
        await callback.answer()


@router.callback_query(F.data == "confirm_create_application")
async def callback_confirm_create_application(callback: CallbackQuery, state: FSMContext):
    """Фактическое создание заявки после подтверждения"""
    await state.clear()
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        
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
        
        # Формируем текст статуса заявки
        wait_time_text = ""
        if application.estimated_wait_time:
            wait_time_text = f"\n⏱ Примерное время ожидания: {format_wait_time(application.estimated_wait_time)}"
        
        status_text = (
            f"📊 Статус заявки #{application.id}\n\n"
            f"✅ Заявка создана!\n"
            f"📊 Статус: {application.status}\n"
        )
        
        if application.queue_position:
            status_text += f"📍 Позиция в очереди: {application.queue_position}{wait_time_text}\n\n"
        else:
            status_text += f"📍 Позиция в очереди: рассчитывается...\n\n"
        
        status_text += "Ожидайте подключения модератора. Вы получите уведомление, когда модератор начнет работу с вашей заявкой."
        
        # Показываем статус заявки в главном сообщении
        from keyboards.user_keyboards import get_application_status_keyboard
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=status_text,
            reply_markup=get_application_status_keyboard(application.id, application.status)
        )
        
        # Отправляем уведомления модераторам о новой заявке
        await notify_moderators_new_application(callback.bot, application)
        
        await callback.answer("Заявка создана!")


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
async def callback_deposit_amount(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора суммы пополнения"""
    await state.clear()
    try:
        amount = int(callback.data.split("_")[-1])
        await create_stars_invoice(callback, amount)
    except ValueError:
        await callback.answer("❌ Ошибка: неверная сумма", show_alert=True)


@router.callback_query(F.data.startswith("retry_payment_"))
async def callback_retry_payment(callback: CallbackQuery, state: FSMContext):
    """Повторить оплату после истечения инвойса"""
    await state.clear()
    
    # Извлекаем сумму из callback_data: "retry_payment_{amount}"
    try:
        amount = int(callback.data.split("_")[-1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка: неверная сумма", show_alert=True)
        return
    
    # Создаем новый инвойс на ту же сумму
    await create_stars_invoice(callback, amount)
    await callback.answer()


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
async def process_payment_amount_invalid(message: Message, state: FSMContext):
    """Обработка неверного формата суммы"""
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
    
    await update_user_main_message(
        bot=message.bot,
        user_id=message.from_user.id,
        text="❌ Пожалуйста, введите целое число (например: 500)",
        reply_markup=get_back_to_menu_keyboard()
    )


async def schedule_invoice_deletion(bot: Bot, user_id: int, invoice_message_id: int, amount: int):
    """Запланировать удаление инвойса через 10 минут, если он не был оплачен"""
    await asyncio.sleep(600)  # 10 минут = 600 секунд
    
    # Проверяем, был ли инвойс оплачен (invoice_message_id должен быть None, если оплачен)
    async for session in get_session():
        user = await get_or_create_user(session, user_id=user_id)
        await session.commit()
        
        # Если invoice_message_id всё ещё установлен, значит инвойс не был оплачен
        if user.invoice_message_id == invoice_message_id:
            try:
                # Удаляем инвойс
                await bot.delete_message(
                    chat_id=user_id,
                    message_id=invoice_message_id
                )
                
                # Очищаем invoice_message_id
                async for session in get_session():
                    user = await get_or_create_user(session, user_id=user_id)
                    user.invoice_message_id = None
                    await session.commit()
                
                # Уведомляем пользователя
                notification_text = (
                    "⏰ Счёт на пополнение баланса был автоматически удалён\n\n"
                    f"💰 Сумма: {amount}⭐\n"
                    "💡 Вы можете создать новый счёт в любое время"
                )
                
                from keyboards.user_keyboards import get_invoice_expired_keyboard
                
                await update_user_main_message(
                    bot=bot,
                    user_id=user_id,
                    text=notification_text,
                    reply_markup=get_invoice_expired_keyboard(amount)
                )
                
                logger.info(
                    f"Инвойс (message_id={invoice_message_id}) автоматически удалён "
                    f"через 10 минут для пользователя {user_id}"
                )
            except TelegramBadRequest as e:
                error_msg = str(e).lower()
                if "message to delete not found" in error_msg or "message not found" in error_msg:
                    # Инвойс уже удалён (возможно, оплачен или удалён вручную)
                    logger.debug(f"Инвойс {invoice_message_id} уже удалён для пользователя {user_id}")
                    # Очищаем invoice_message_id
                    async for session in get_session():
                        user = await get_or_create_user(session, user_id=user_id)
                        if user.invoice_message_id == invoice_message_id:
                            user.invoice_message_id = None
                            await session.commit()
                else:
                    logger.error(f"Ошибка при удалении инвойса {invoice_message_id} для пользователя {user_id}: {e}")
            except Exception as e:
                logger.error(f"Ошибка при автоматическом удалении инвойса {invoice_message_id}: {e}")


async def create_stars_invoice(callback_or_message, amount: int):
    """Создать инвойс для оплаты через Telegram Stars"""
    from aiogram.types import LabeledPrice
    
    user_id = callback_or_message.from_user.id
    timestamp = int(datetime.utcnow().timestamp())
    payload = f"deposit_{user_id}_{amount}_{timestamp}"
    
    title = f"Пополнение баланса на {amount}⭐"
    # Улучшенное описание с предупреждением о времени действия
    description = (
        f"💰 Пополнение баланса в боте на {amount} Telegram Stars\n\n"
        f"⏰ Счёт действителен 10 минут\n"
        f"⚠️ После истечения времени счёт будет автоматически удалён"
    )
    
    # Для Telegram Stars используем currency='XTR'
    # Сумма указывается напрямую в Stars (не в центах!)
    # provider_token должен быть опущен (не пустая строка!)
    prices = [LabeledPrice(label=f"{amount} Stars", amount=amount)]
    
    try:
        sent_message = None
        bot = callback_or_message.bot if isinstance(callback_or_message, CallbackQuery) else callback_or_message.bot
        
        if isinstance(callback_or_message, CallbackQuery):
            sent_message = await callback_or_message.message.answer_invoice(
                title=title,
                description=description,
                payload=payload,
                currency="XTR",  # Telegram Stars
                prices=prices,
                # provider_token не указываем для Stars!
            )
            await callback_or_message.answer()
        else:
            sent_message = await callback_or_message.answer_invoice(
                title=title,
                description=description,
                payload=payload,
                currency="XTR",  # Telegram Stars
                prices=prices,
                # provider_token не указываем для Stars!
            )
        
        # Сохраняем message_id инвойса для возможности удаления
        if sent_message:
            from database.queries import set_user_invoice_message_id
            async for session in get_session():
                await set_user_invoice_message_id(session, user_id, sent_message.message_id)
                await session.commit()
            
            # Запускаем задачу для автоматического удаления через 10 минут
            asyncio.create_task(
                schedule_invoice_deletion(bot, user_id, sent_message.message_id, amount)
            )
        
        logger.info(f"Создан инвойс для пользователя {user_id}: {amount}⭐, message_id={sent_message.message_id if sent_message else 'N/A'}")
        
    except Exception as e:
        logger.error(f"Ошибка при создании инвойса: {e}", exc_info=True)
        error_text = (
            "❌ Не удалось создать счёт для оплаты.\n"
            "Пожалуйста, попробуйте позже или свяжитесь с администратором."
        )
        user_id = callback_or_message.from_user.id
        bot = callback_or_message.bot if isinstance(callback_or_message, CallbackQuery) else callback_or_message.bot
        
        await update_user_main_message(
            bot=bot,
            user_id=user_id,
            text=error_text,
            reply_markup=get_back_to_menu_keyboard()
        )
        
        if isinstance(callback_or_message, CallbackQuery):
            await callback_or_message.answer("Ошибка", show_alert=True)


async def create_stars_invoice_message(message: Message, amount: int):
    """Создать инвойс для оплаты через Telegram Stars (для message)"""
    await create_stars_invoice(message, amount)


@router.callback_query(F.data == "my_applications")
async def callback_my_applications(callback: CallbackQuery, state: FSMContext):
    """Показать список заявок пользователя"""
    await state.clear()
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


@router.callback_query(F.data == "faq")
async def callback_faq(callback: CallbackQuery, state: FSMContext):
    """Заглушка: F.A.Q"""
    await state.clear()
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        is_moderator_user = is_moderator_or_admin(user)
        is_admin_user = user.role == ROLE_ADMIN
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="Раздел F.A.Q в разработке.",
            reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user, is_admin=is_admin_user),
        )
    await callback.answer()


@router.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery, state: FSMContext):
    """Заглушка: Поддержка"""
    await state.clear()
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        is_moderator_user = is_moderator_or_admin(user)
        is_admin_user = user.role == ROLE_ADMIN
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="Раздел поддержки в разработке.",
            reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user, is_admin=is_admin_user),
        )
    await callback.answer()


@router.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery, state: FSMContext):
    """Заглушка: Реферальная программа"""
    await state.clear()
    async for session in get_session():
        user = await get_or_create_user(session, user_id=callback.from_user.id)
        await session.commit()
        is_moderator_user = is_moderator_or_admin(user)
        is_admin_user = user.role == ROLE_ADMIN
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text="Реферальная программа в разработке.",
            reply_markup=get_main_menu_keyboard(is_moderator=is_moderator_user, is_admin=is_admin_user),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("view_application_"))
async def callback_view_application(callback: CallbackQuery, state: FSMContext):
    """Просмотр конкретной заявки"""
    await state.clear()
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
            "rejected": "❌",
            "cancelled": "🚫"
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
            reply_markup=get_application_status_keyboard(application_id, application.status)
        )
        await callback.answer()


@router.callback_query(F.data.startswith("cancel_application_"))
async def callback_cancel_application(callback: CallbackQuery, state: FSMContext):
    """Отменить заявку"""
    await state.clear()
    application_id = int(callback.data.split("_")[-1])
    
    try:
        # Отменяем заявку и возвращаем средства
        from database.queries import cancel_application
        async for session in get_session():
            user = await get_or_create_user(session, user_id=callback.from_user.id)
            application = await get_application_by_id(session, application_id)
            
            if not application or application.user_id != callback.from_user.id:
                await callback.answer("❌ Заявка не найдена", show_alert=True)
                await session.rollback()
                return
            
            if application.status != "pending":
                await callback.answer(
                    "❌ Можно отменить только заявки в статусе 'ожидание'",
                    show_alert=True
                )
                await session.rollback()
                return
            
            await cancel_application(session, application, user)
            await session.commit()
        
        # Показываем подтверждение отмены
        cancel_text = (
            f"✅ Заявка #{application_id} отменена\n\n"
            f"💰 Средства возвращены на ваш баланс\n"
            f"💵 Возвращено: {APPLICATION_COST}⭐"
        )
        
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=cancel_text,
            reply_markup=get_back_to_menu_keyboard()
        )
        
        await callback.answer("Заявка отменена")
        
    except ValueError as e:
        await callback.answer(f"❌ {str(e)}", show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при отмене заявки #{application_id}: {e}", exc_info=True)
        await callback.answer("❌ Произошла ошибка при отмене заявки", show_alert=True)


@router.callback_query(F.data.startswith("confirm_moderator_photo_"))
async def callback_confirm_moderator_photo(callback: CallbackQuery, state: FSMContext):
    """Подтверждение получения фото от модератора и удаление временных сообщений"""
    await state.clear()
    session_id = int(callback.data.split("_")[-1])
    
    async for session in get_session():
        moderation_session = await get_moderation_session_by_id(session, session_id)
        await session.commit()
        
        if not moderation_session or moderation_session.user_id != callback.from_user.id:
            await callback.answer("❌ Сессия не найдена", show_alert=True)
            return
        
        # Удаляем сообщение с фото
        if moderation_session.moderator_photo_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.from_user.id,
                    message_id=moderation_session.moderator_photo_message_id
                )
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение с фото: {e}")
        
        # Удаляем информационное сообщение
        if moderation_session.user_info_message_id:
            try:
                await callback.bot.delete_message(
                    chat_id=callback.from_user.id,
                    message_id=moderation_session.user_info_message_id
                )
            except Exception as e:
                logger.warning(f"Не удалось удалить информационное сообщение: {e}")
        
        # Очищаем message_id в БД
        async for session in get_session():
            moderation_session = await get_moderation_session_by_id(session, session_id)
            if moderation_session:
                moderation_session.moderator_photo_message_id = None
                moderation_session.user_info_message_id = None
                await session.commit()
        
        await callback.answer("✅ Подтверждение получено!")


@router.callback_query(F.data.startswith("refresh_application_"))
async def callback_refresh_application(callback: CallbackQuery, state: FSMContext):
    """Обновить статус заявки"""
    await state.clear()
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
    logger.info(
        "[USER_PHOTO] Шаг 1/6: Бот получил фото. Обработчик: process_user_screenshot (handlers.user_handlers). "
        f"user_id={message.from_user.id}, chat_id={message.chat.id}, message_id={message.message_id}"
    )
    # Проверяем, не является ли это фото от модератора (модератор в состоянии ожидания фото)
    current_state = await state.get_state()
    if current_state and str(current_state) == str(ModeratorStates.waiting_for_moderator_photo):
        logger.debug(f"[USER_PHOTO] Пропуск: это фото от модератора {message.from_user.id}")
        return

    photo: PhotoSize = message.photo[-1]
    file_id = photo.file_id
    photo_message_id = message.message_id
    logger.info(f"[USER_PHOTO] Шаг 2/6: Сохранён message_id сообщения со скриншотом для удаления: {photo_message_id}")

    async for session in get_session():
        session_obj = await get_active_moderation_session_by_user(
            session,
            message.from_user.id
        )

        if not session_obj:
            logger.info("[USER_PHOTO] Нет активной сессии модерации у пользователя — фото не обрабатываем")
            return

        logger.info(
            f"[USER_PHOTO] Шаг 3/6: Найдена активная сессия. application_id={session_obj.application_id}, "
            f"moderator_id={session_obj.moderator_id}. Сохраняем file_id, отправляем скриншот модератору."
        )
        await set_session_user_photo(session, session_obj, file_id)

        bot = message.bot
        from database.queries import set_moderator_screenshot_message_id

        try:
            sent_message = await bot.send_photo(
                chat_id=session_obj.moderator_id,
                photo=file_id,
                caption=f"📸 Скриншот от пользователя (Заявка #{session_obj.application_id})"
            )
            await set_moderator_screenshot_message_id(
                session, session_obj.id, sent_message.message_id
            )
            logger.info(
                f"[USER_PHOTO] Шаг 4/6: Скриншот отправлен модератору. Сохранён moderator_screenshot_message_id={sent_message.message_id}"
            )
        except Exception as e:
            logger.error(f"[USER_PHOTO] Ошибка отправки скриншота модератору: {e}")
            await session.rollback()
            return

        await session.commit()

        from utils.user_messages import delete_user_photo_message

        logger.info(
            f"[USER_PHOTO] Шаг 5/6: Вызов delete_user_photo_message(bot, chat_id={message.chat.id}, message_id={photo_message_id}). "
            "Функция: utils.user_messages.delete_user_photo_message"
        )
        deleted = await delete_user_photo_message(
            bot=bot,
            chat_id=message.chat.id,
            message_id=photo_message_id
        )

        logger.info(
            f"[USER_PHOTO] Шаг 6/6: Результат удаления сообщения в чате пользователя: deleted={deleted}. "
            f"message_id={photo_message_id}, chat_id={message.chat.id}"
        )
        if not deleted:
            logger.warning(
                "[USER_PHOTO] Сообщение пользователя не удалено (в личном чате бот не может удалять сообщения пользователя — ограничение Telegram)."
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
async def process_user_screenshot_invalid(message: Message, state: FSMContext):
    """Обработка некорректного сообщения вместо скриншота"""
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
