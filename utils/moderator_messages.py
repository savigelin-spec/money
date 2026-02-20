"""
Утилиты для управления сообщениями модератора
"""
import logging
from typing import Optional
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from database.db import get_session
from database.queries import (
    get_or_create_user,
    set_user_main_message_id,
    get_moderator_notifications_for_application,
    get_moderation_session_by_application_id,
)
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


async def delete_moderator_notifications_for_application(
    bot: Bot,
    application_id: int,
) -> None:
    """
    Удалить все уведомления модераторов о заявке.
    Вызывается после обработки заявки (approve/reject).
    """
    async for session in get_session():
        notifications = await get_moderator_notifications_for_application(
            session, application_id
        )
        await session.commit()
        
        # Удаляем сообщения в Telegram
        for notification in notifications:
            try:
                await bot.delete_message(
                    chat_id=notification.moderator_id,
                    message_id=notification.message_id
                )
                logger.info(
                    f"Удалено уведомление о заявке #{application_id} "
                    f"для модератора {notification.moderator_id}"
                )
            except TelegramBadRequest as e:
                error_msg = str(e).lower()
                if "message to delete not found" in error_msg or "message not found" in error_msg:
                    logger.debug(
                        f"Уведомление {notification.message_id} уже удалено "
                        f"для модератора {notification.moderator_id}"
                    )
                else:
                    logger.error(
                        f"Ошибка при удалении уведомления {notification.message_id} "
                        f"для модератора {notification.moderator_id}: {e}"
                    )
        
        # Удаляем записи из БД
        async for session in get_session():
            for notification in notifications:
                await session.delete(notification)
            await session.commit()


async def delete_moderator_screenshot_message_for_application(
    bot: Bot,
    application_id: int,
    moderator_id: int | None = None,
    message_id: int | None = None,
) -> None:
    """
    Удалить сообщение «Скриншот от пользователя» в чате модератора после обработки заявки.
    Вызывается после approve/reject вместе с delete_moderator_notifications_for_application.
    
    Если переданы moderator_id и message_id, использует их напрямую.
    Иначе ищет сессию по application_id.
    """
    # Если переданы данные напрямую, используем их
    if moderator_id is not None and message_id is not None:
        logger.info(f"Удаление сообщения со скриншотом {message_id} у модератора {moderator_id} для заявки #{application_id}")
        try:
            await bot.delete_message(
                chat_id=moderator_id,
                message_id=message_id,
            )
            logger.info(
                f"Удалено сообщение со скриншотом {message_id} у модератора {moderator_id} "
                f"для заявки #{application_id}"
            )
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message to delete not found" in error_msg or "message not found" in error_msg:
                logger.debug(
                    f"Сообщение со скриншотом {message_id} уже удалено у модератора {moderator_id}"
                )
            else:
                logger.warning(
                    f"Не удалось удалить сообщение со скриншотом {message_id} у модератора {moderator_id}: {e}"
                )
        
        # Обнуляем поле в БД
        async for session in get_session():
            mod_session = await get_moderation_session_by_application_id(
                session, application_id
            )
            if mod_session:
                mod_session.moderator_screenshot_message_id = None
                await session.commit()
        return
    
    # Иначе ищем сессию по application_id
    logger.info(f"Попытка удалить сообщение со скриншотом для заявки #{application_id}")
    async for session in get_session():
        mod_session = await get_moderation_session_by_application_id(
            session, application_id
        )

        if not mod_session:
            logger.warning(f"Сессия модерации не найдена для заявки #{application_id}")
            return
        
        if not mod_session.moderator_screenshot_message_id:
            logger.debug(f"moderator_screenshot_message_id не установлен для заявки #{application_id}")
            return

        # Читаем поля в переменные до любых операций с БД
        moderator_id = mod_session.moderator_id
        msg_id = mod_session.moderator_screenshot_message_id
        logger.info(f"Найдена сессия для заявки #{application_id}, moderator_id={moderator_id}, msg_id={msg_id}")

        try:
            await bot.delete_message(
                chat_id=moderator_id,
                message_id=msg_id,
            )
            logger.info(
                f"Удалено сообщение со скриншотом {msg_id} у модератора {moderator_id} "
                f"для заявки #{application_id}"
            )
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message to delete not found" in error_msg or "message not found" in error_msg:
                logger.debug(
                    f"Сообщение со скриншотом {msg_id} уже удалено у модератора {moderator_id}"
                )
            else:
                logger.warning(
                    f"Не удалось удалить сообщение со скриншотом {msg_id} у модератора {moderator_id}: {e}"
                )

        # Обнуляем поле в БД в той же сессии
        mod_session.moderator_screenshot_message_id = None
        await session.commit()
        return


async def delete_moderator_own_photo_message_for_application(
    bot: Bot,
    application_id: int,
    moderator_id: int | None = None,
    message_id: int | None = None,
) -> None:
    """
    Удалить сообщение с фото модератора в его чате после обработки заявки.
    Вызывается после approve/reject вместе с delete_moderator_screenshot_message_for_application.
    
    Если переданы moderator_id и message_id, использует их напрямую.
    Иначе ищет сессию по application_id.
    """
    # Если переданы данные напрямую, используем их
    if moderator_id is not None and message_id is not None:
        logger.info(
            f"[MOD_PHOTO] delete_moderator_own_photo_message: вызов bot.delete_message "
            f"chat_id={moderator_id}, message_id={message_id}, application_id={application_id}"
        )
        try:
            await bot.delete_message(
                chat_id=moderator_id,
                message_id=message_id,
            )
            logger.info(
                f"[MOD_PHOTO] Сообщение с фото модератора {message_id} удалено у модератора {moderator_id} "
                f"для заявки #{application_id}"
            )
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message to delete not found" in error_msg or "message not found" in error_msg:
                logger.debug(
                    f"[MOD_PHOTO] Сообщение {message_id} уже удалено у модератора {moderator_id}"
                )
            else:
                logger.warning(
                    f"[MOD_PHOTO] Не удалось удалить сообщение с фото модератора {message_id} "
                    f"у модератора {moderator_id}: {e}"
                )
        
        # Обнуляем поле в БД
        async for session in get_session():
            mod_session = await get_moderation_session_by_application_id(
                session, application_id
            )
            if mod_session:
                mod_session.moderator_own_photo_message_id = None
                await session.commit()
        return
    
    # Иначе ищем сессию по application_id
    logger.info(f"[MOD_PHOTO] Попытка удалить сообщение с фото модератора для заявки #{application_id}")
    async for session in get_session():
        mod_session = await get_moderation_session_by_application_id(
            session, application_id
        )

        if not mod_session:
            logger.warning(f"Сессия модерации не найдена для заявки #{application_id}")
            return
        
        if not mod_session.moderator_own_photo_message_id:
            logger.debug(f"[MOD_PHOTO] moderator_own_photo_message_id не установлен для заявки #{application_id}")
            return

        # Читаем поля в переменные до любых операций с БД
        moderator_id = mod_session.moderator_id
        msg_id = mod_session.moderator_own_photo_message_id
        logger.info(f"[MOD_PHOTO] Найдена сессия для заявки #{application_id}, moderator_id={moderator_id}, msg_id={msg_id}")

        try:
            await bot.delete_message(
                chat_id=moderator_id,
                message_id=msg_id,
            )
            logger.info(
                f"[MOD_PHOTO] Удалено сообщение с фото модератора {msg_id} у модератора {moderator_id} "
                f"для заявки #{application_id}"
            )
        except TelegramBadRequest as e:
            error_msg = str(e).lower()
            if "message to delete not found" in error_msg or "message not found" in error_msg:
                logger.debug(
                    f"[MOD_PHOTO] Сообщение {msg_id} уже удалено у модератора {moderator_id}"
                )
            else:
                logger.warning(
                    f"[MOD_PHOTO] Не удалось удалить сообщение с фото модератора {msg_id} "
                    f"у модератора {moderator_id}: {e}"
                )

        # Обнуляем поле в БД в той же сессии
        mod_session.moderator_own_photo_message_id = None
        await session.commit()
        return
