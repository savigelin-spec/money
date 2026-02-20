"""
Утилиты для управления сообщениями модератора
"""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from database.db import get_session
from database.queries import get_or_create_user, set_user_main_message_id
from utils.telegram_helpers import safe_edit_message_text

logger = logging.getLogger(__name__)


async def get_or_create_moderator_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup=None,
) -> Optional[int]:
    """
    Получить или создать главное сообщение модератора.
    Возвращает message_id.
    """
    async for session in get_session():
        user, _ = await get_or_create_user(session, user_id=user_id)
        await session.commit()

        # Если сообщение уже существует, пытаемся его отредактировать
        if user.main_message_id:
            try:
                status = await safe_edit_message_text(
                    bot=bot,
                    chat_id=user_id,
                    message_id=user.main_message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                if status in ["edited", "not_modified"]:
                    return user.main_message_id
                # Если safe_edit_message_text вернул ошибку, создаем новое сообщение
                logger.warning(f"Не удалось отредактировать сообщение модератора {user_id}, создаем новое")
                user.main_message_id = None
            except TelegramBadRequest as e:
                err = str(e).lower()
                if "message to edit not found" in err or "message can't be edited" in err:
                    logger.warning(f"Главное сообщение модератора {user.main_message_id} недоступно, создаем новое")
                    user.main_message_id = None
                else:
                    logger.error("Ошибка при редактировании сообщения модератора user_id=%s message_id=%s: %s", user_id, user.main_message_id, e)
                    user.main_message_id = None

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
            logger.error(f"Ошибка при создании главного сообщения для модератора {user_id}: {e}")
            await session.rollback()
            return None


async def update_moderator_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup=None,
    message_id: Optional[int] = None,
    chat_id: Optional[int] = None,
) -> bool:
    """
    Обновить главное сообщение модератора.
    Если передан message_id (из callback), сначала редактируем это сообщение и при успехе обновляем main_message_id.
    """
    target_chat_id = chat_id if chat_id is not None else user_id

    async for session in get_session():
        user, _ = await get_or_create_user(session, user_id=user_id)
        await session.commit()

        if message_id is not None:
            try:
                status = await safe_edit_message_text(
                    bot=bot,
                    chat_id=target_chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                )
                if status in ["edited", "not_modified"]:
                    if message_id != user.main_message_id:
                        await set_user_main_message_id(session, user_id, message_id)
                        await session.commit()
                    return True
            except TelegramBadRequest as e:
                err = str(e).lower()
                if "message is not modified" in err:
                    return True
                if "message to edit not found" in err or "message can't be edited" in err:
                    logger.warning(
                        "Сообщение модератора недоступно (message_id=%s), пробуем main_message_id",
                        message_id,
                    )
                else:
                    logger.error(
                        "Ошибка при редактировании сообщения модератора user_id=%s message_id=%s: %s",
                        user_id,
                        message_id,
                        e,
                    )
                    return False

        if not user.main_message_id:
            await get_or_create_moderator_message(bot, user_id, text, reply_markup)
            return True

        try:
            status = await safe_edit_message_text(
                bot=bot,
                chat_id=user_id,
                message_id=user.main_message_id,
                text=text,
                reply_markup=reply_markup,
            )
            if status in ["edited", "not_modified"]:
                return True
            logger.warning("Не удалось отредактировать сообщение модератора %s, создаем новое", user_id)
            user.main_message_id = None
            await session.commit()
            await get_or_create_moderator_message(bot, user_id, text, reply_markup)
            return True
        except TelegramBadRequest as e:
            err = str(e).lower()
            if "message is not modified" in err:
                return True
            if "message to edit not found" in err or "message can't be edited" in err:
                logger.warning(
                    "Главное сообщение модератора %s недоступно для user_id=%s, создаем новое",
                    user.main_message_id,
                    user_id,
                )
                user.main_message_id = None
                await session.commit()
                await get_or_create_moderator_message(bot, user_id, text, reply_markup)
                return True
            logger.error("Ошибка при редактировании главного сообщения модератора user_id=%s: %s", user_id, e)
            return False
