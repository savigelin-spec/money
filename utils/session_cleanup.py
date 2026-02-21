"""
Единая очистка сообщений сессии при завершении (лайв-чат, фото, инфо-сообщения).
"""
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from database.queries import (
    get_session_message_ids,
    delete_session_message_rows,
    get_moderation_session_by_id,
)

logger = logging.getLogger(__name__)


async def _safe_delete_message(bot: Bot, chat_id: int, message_id: int, label: str = "") -> None:
    """Удалить сообщение в Telegram, логировать ошибки без падения."""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug("Удалено сообщение %s chat_id=%s message_id=%s", label, chat_id, message_id)
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message to delete not found" in err or "message not found" in err:
            logger.debug("Сообщение %s уже удалено chat_id=%s message_id=%s", label, chat_id, message_id)
        else:
            logger.warning("Не удалось удалить сообщение %s chat_id=%s message_id=%s: %s", label, chat_id, message_id, e)


async def delete_all_session_messages(
    bot: Bot,
    db_session: AsyncSession,
    session_id: int,
) -> None:
    """
    Удалить все сообщения сессии у пользователя и модератора:
    - сообщения из лайв-чата (moderation_session_messages): и сообщения бота, и оригиналы
      сообщений/фото пользователя и модератора (удаление оригиналов пытаемся выполнить при
      завершении сессии; в личных чатах Telegram может не разрешить удаление чужих сообщений);
    - user_info_message_id, moderator_photo_message_id в чате пользователя,
    - moderator_screenshot_message_id, moderator_own_photo_message_id в чате модератора,
    - оповещения о заявке у модераторов («Новая заявка #N»), чтобы в чате оставалось только главное меню.
    Поля в БД обнуляются, записи moderation_session_messages удаляются.
    """
    mod_session = await get_moderation_session_by_id(db_session, session_id)
    if not mod_session:
        logger.warning("Сессия %s не найдена для очистки сообщений", session_id)
        return

    user_id = mod_session.user_id
    moderator_id = mod_session.moderator_id

    # 1) Удалить сообщения лайв-чата
    for chat_id, message_id in await get_session_message_ids(db_session, session_id):
        await _safe_delete_message(bot, chat_id, message_id, "live_chat")
    await delete_session_message_rows(db_session, session_id)

    # 2) Удалить сообщения из полей сессии
    if mod_session.user_info_message_id:
        await _safe_delete_message(
            bot, user_id, mod_session.user_info_message_id, "user_info"
        )
        mod_session.user_info_message_id = None
    if mod_session.moderator_photo_message_id:
        await _safe_delete_message(
            bot, user_id, mod_session.moderator_photo_message_id, "moderator_photo"
        )
        mod_session.moderator_photo_message_id = None
    if mod_session.moderator_screenshot_message_id:
        await _safe_delete_message(
            bot, moderator_id, mod_session.moderator_screenshot_message_id, "moderator_screenshot"
        )
        mod_session.moderator_screenshot_message_id = None
    if mod_session.moderator_own_photo_message_id:
        await _safe_delete_message(
            bot, moderator_id, mod_session.moderator_own_photo_message_id, "moderator_own_photo"
        )
        mod_session.moderator_own_photo_message_id = None

    await db_session.flush()

    from utils.moderator_messages import delete_moderator_notifications_for_application
    await delete_moderator_notifications_for_application(bot, mod_session.application_id, db_session)

    logger.info("Очистка сообщений сессии #%s выполнена", session_id)
