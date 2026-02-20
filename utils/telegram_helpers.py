"""
Вспомогательные функции для работы с Telegram API (безопасное редактирование и т.д.).
"""
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest


async def safe_edit_message_text(
    bot: Bot,
    chat_id: int,
    message_id: int,
    text: str,
    reply_markup=None,
) -> str:
    """
    Редактирует текст сообщения. При ошибке «message is not modified»
    не пробрасывает исключение.
    Возвращает "edited" при успешном изменении, "not_modified" если контент тот же.
    """
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return "edited"
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return "not_modified"
        raise
