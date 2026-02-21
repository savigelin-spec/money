"""
Клавиатуры для модераторов
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_moderator_panel_keyboard() -> InlineKeyboardMarkup:
    """Панель модератора"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Доступные заявки",
                callback_data="moderator_pending_applications"
            )
        ],
        [
            InlineKeyboardButton(
                text="🔄 Мои активные сессии",
                callback_data="moderator_active_sessions"
            )
        ],
        [
            InlineKeyboardButton(
                text="📸 Сессии без фото",
                callback_data="moderator_sessions_without_photo"
            )
        ],
        [
            InlineKeyboardButton(
                text="📊 Статистика",
                callback_data="moderator_stats"
            )
        ],
        [
            InlineKeyboardButton(
                text="◀️ Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    return keyboard


def get_pending_applications_keyboard(applications: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком ожидающих заявок"""
    buttons = []
    for app in applications:
        queue_info = f"Позиция: {app.queue_position}" if app.queue_position else "В очереди"
        buttons.append([
            InlineKeyboardButton(
                text=f"📝 Заявка #{app.id} ({queue_info})",
                callback_data=f"moderator_take_application_{app.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Панель модератора",
            callback_data="moderator_panel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_moderation_session_keyboard(
    session_id: int,
    is_completed: bool = False,
    user_inactive_minutes: float | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура для сессии модерации.
    Одна кнопка «Завершить заявку»: 🔴 если < 3 мин с последнего сообщения пользователя, 🟢 если >= 3 мин.
    """
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    if not is_completed:
        # Одна кнопка: красная (< 3 мин) или зелёная (>= 3 мин)
        if user_inactive_minutes is not None and user_inactive_minutes >= 3:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="🟢 Завершить заявку",
                    callback_data=f"moderator_end_request_{session_id}"
                )
            ])
        else:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(
                    text="🔴 Завершить заявку",
                    callback_data=f"moderator_end_request_{session_id}"
                )
            ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="◀️ Панель модератора",
            callback_data="moderator_panel"
        )
    ])
    
    return keyboard


def get_active_sessions_keyboard(sessions: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком активных сессий модератора"""
    buttons = []
    for session in sessions:
        buttons.append([
            InlineKeyboardButton(
                text=f"🔄 Сессия #{session.id} (Заявка #{session.application_id})",
                callback_data=f"moderator_session_{session.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Панель модератора",
            callback_data="moderator_panel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
