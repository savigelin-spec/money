"""
Хелперы для «красивых» inline-кнопок: цветной фон и эмодзи.

Требуется Telegram Bot API 9.4+ и aiogram >= 3.25.

- style: 'primary' (синий), 'success' (зелёный), 'danger' (красный).
- Обычные эмодзи — просто в text (например "✅ Подтвердить").
- Премиум-эмодзи в кнопках — через icon_custom_emoji_id (нужен Premium у владельца бота
  или доп. username на Fragment).
- Кнопки с url= показывают иконку ↗ автоматически.

Пример кнопки-ссылки:
    styled_button("🔗 Открыть сайт", url="https://example.com", style=STYLE_PRIMARY)
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Стили кнопок (Bot API 9.4)
STYLE_PRIMARY = "primary"   # синий
STYLE_SUCCESS = "success"   # зелёный
STYLE_DANGER = "danger"     # красный


def styled_button(
    text: str,
    *,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
    icon_custom_emoji_id: str | None = None,
) -> InlineKeyboardButton:
    """
    Inline-кнопка с опциональным цветом и премиум-эмодзи.

    :param text: Текст кнопки (можно с обычными Unicode-эмодзи).
    :param callback_data: Данные при нажатии (взаимоисключающе с url и др.).
    :param url: Ссылка при нажатии — в клиенте покажется иконка ↗.
    :param style: 'primary' | 'success' | 'danger'.
    :param icon_custom_emoji_id: ID кастомного (премиум) эмодзи перед текстом.
    """
    kwargs = {
        "text": text,
        "icon_custom_emoji_id": icon_custom_emoji_id,
        "style": style,
    }
    if url is not None:
        kwargs["url"] = url
    elif callback_data is not None:
        kwargs["callback_data"] = callback_data
    else:
        raise ValueError("Нужен ровно один из: callback_data, url")
    return InlineKeyboardButton(**kwargs)
