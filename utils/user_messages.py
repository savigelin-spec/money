"""
Утилиты для управления сообщениями пользователя
"""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from database.db import get_session
from database.queries import (
    get_or_create_user,
    get_active_moderation_session_by_user,
    set_user_main_message_id,
    set_user_info_message_id,
    get_user_message_ids,
)

logger = logging.getLogger(__name__)


async def get_or_create_user_main_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup=None,
) -> Optional[int]:
    """
    Получить или создать главное сообщение пользователя с меню.
    Возвращает message_id.
    """
    async for session in get_session():
        user = await get_or_create_user(session, user_id=user_id)
        await session.commit()

        # Если сообщение уже существует, пытаемся его отредактировать
        if user.main_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=user.main_message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                return user.main_message_id
            except TelegramBadRequest as e:
                # Сообщение удалено или недоступно - создаем новое
                if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                    logger.warning(f"Главное сообщение {user.main_message_id} недоступно, создаем новое")
                    user.main_message_id = None
                else:
                    raise

        # Создаем новое сообщение
        try:
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
            )
            message_id = sent_message.message_id

            # Сохраняем message_id в БД
            await set_user_main_message_id(session, user_id, message_id)
            await session.commit()

            return message_id
        except Exception as e:
            logger.error(f"Ошибка при создании главного сообщения для пользователя {user_id}: {e}")
            await session.rollback()
            return None


async def update_user_main_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup=None,
) -> bool:
    """
    Обновить главное сообщение пользователя.
    Возвращает True если успешно, False если нужно создать новое.
    """
    async for session in get_session():
        user = await get_or_create_user(session, user_id=user_id)
        await session.commit()

        if not user.main_message_id:
            # Если нет message_id, создаем новое сообщение
            await get_or_create_user_main_message(bot, user_id, text, reply_markup)
            return True

        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=user.main_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            return True
        except TelegramBadRequest as e:
            # Сообщение удалено или недоступно - создаем новое
            if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                logger.warning(f"Главное сообщение {user.main_message_id} недоступно, создаем новое")
                user.main_message_id = None
                await session.commit()
                await get_or_create_user_main_message(bot, user_id, text, reply_markup)
                return True
            else:
                logger.error(f"Ошибка при редактировании главного сообщения: {e}")
                return False


async def get_or_create_user_info_message(
    bot: Bot,
    user_id: int,
    text: str,
) -> Optional[int]:
    """
    Получить или создать информационное сообщение пользователя.
    Возвращает message_id.
    """
    async for session in get_session():
        # Получаем активную сессию пользователя
        moderation_session = await get_active_moderation_session_by_user(session, user_id)

        if not moderation_session:
            # Если нет активной сессии, не создаем информационное сообщение
            return None

        # Если сообщение уже существует, пытаемся его отредактировать
        if moderation_session.user_info_message_id:
            try:
                await bot.edit_message_text(
                    chat_id=user_id,
                    message_id=moderation_session.user_info_message_id,
                    text=text,
                )
                return moderation_session.user_info_message_id
            except TelegramBadRequest as e:
                # Сообщение удалено или недоступно - создаем новое
                if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                    logger.warning(f"Информационное сообщение {moderation_session.user_info_message_id} недоступно, создаем новое")
                    moderation_session.user_info_message_id = None
                else:
                    raise

        # Создаем новое сообщение
        try:
            sent_message = await bot.send_message(
                chat_id=user_id,
                text=text,
            )
            message_id = sent_message.message_id

            # Сохраняем message_id в БД
            await set_user_info_message_id(session, moderation_session.id, message_id)
            await session.commit()

            return message_id
        except Exception as e:
            logger.error(f"Ошибка при создании информационного сообщения для пользователя {user_id}: {e}")
            await session.rollback()
            return None


async def update_user_info_message(
    bot: Bot,
    user_id: int,
    text: str,
) -> bool:
    """
    Обновить информационное сообщение пользователя.
    Возвращает True если успешно, False если сообщение не обновлено.
    """
    async for session in get_session():
        # Получаем активную сессию пользователя
        moderation_session = await get_active_moderation_session_by_user(session, user_id)

        if not moderation_session:
            # Если нет активной сессии, не обновляем
            return False

        if not moderation_session.user_info_message_id:
            # Если нет message_id, создаем новое сообщение
            await get_or_create_user_info_message(bot, user_id, text)
            return True

        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=moderation_session.user_info_message_id,
                text=text,
            )
            return True
        except TelegramBadRequest as e:
            # Сообщение удалено или недоступно - создаем новое
            if "message to edit not found" in str(e).lower() or "message can't be edited" in str(e).lower():
                logger.warning(f"Информационное сообщение {moderation_session.user_info_message_id} недоступно, создаем новое")
                moderation_session.user_info_message_id = None
                await session.commit()
                await get_or_create_user_info_message(bot, user_id, text)
                return True
            else:
                logger.error(f"Ошибка при редактировании информационного сообщения: {e}")
                return False


async def delete_user_photo_message(
    bot: Bot,
    chat_id: int,
    message_id: int,
) -> bool:
    """
    Удалить сообщение со скриншотом пользователя.
    Возвращает True если успешно удалено.
    
    ВАЖНО: В личном чате бот НЕ МОЖЕТ удалять сообщения пользователя!
    Бот может удалять только свои собственные сообщения.
    Это ограничение Telegram Bot API.
    """
    try:
        logger.info(f"Попытка удалить сообщение {message_id} в чате {chat_id}")
        result = await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Сообщение {message_id} успешно удалено. Результат: {result}")
        return True
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        error_code = getattr(e, 'error_code', None)
        logger.error(
            f"TelegramBadRequest при удалении сообщения {message_id}: "
            f"Код ошибки: {error_code}, Сообщение: {e}"
        )
        
        # Сообщение уже удалено или недоступно
        if "message to delete not found" in error_msg or "message not found" in error_msg:
            logger.debug(f"Сообщение {message_id} уже удалено или не найдено")
            return True
        # Бот не может удалять сообщения пользователя в личном чате
        elif "can't delete" in error_msg or "bad request" in error_msg or error_code == 400:
            logger.warning(
                f"Не удалось удалить сообщение {message_id}: {e}\n"
                f"В личном чате бот не может удалять сообщения пользователя. "
                f"Это ограничение Telegram Bot API. Бот может удалять только свои сообщения."
            )
            return False
        else:
            logger.warning(f"Не удалось удалить сообщение {message_id}: {e}")
            return False
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения {message_id}: {e}", exc_info=True)
        return False
