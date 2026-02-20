"""
Клавиатуры для пользователей
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import APPLICATION_COST


def get_main_menu_keyboard(is_moderator: bool = False) -> InlineKeyboardMarkup:
    """Главное меню пользователя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Подать заявку на подтверждение ({APPLICATION_COST}⭐)",
                callback_data="create_application"
            )
        ],
        [
            InlineKeyboardButton(
                text="Мой баланс",
                callback_data="show_balance"
            ),
            InlineKeyboardButton(
                text="Пополнить баланс",
                callback_data="deposit_balance"
            )
        ],
        [
            InlineKeyboardButton(
                text="Мои заявки",
                callback_data="my_applications"
            )
        ]
    ])
    
    # Добавляем кнопку для модераторов
    if is_moderator:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="👮 Перейти в модераторы",
                callback_data="go_to_moderator_panel"
            )
        ])
    
    return keyboard


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Кнопка возврата в главное меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="◀️ Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    return keyboard


def get_application_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения создания заявки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data="confirm_create_application"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data="main_menu"
            )
        ]
    ])
    return keyboard


def get_invoice_expired_keyboard(amount: int) -> InlineKeyboardMarkup:
    """Клавиатура при истечении инвойса с опциями повтора оплаты и возврата в меню"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🔄 Повторить оплату",
                callback_data=f"retry_payment_{amount}"
            ),
            InlineKeyboardButton(
                text="◀️ Главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    return keyboard


def get_application_status_keyboard(application_id: int, status: str = "pending") -> InlineKeyboardMarkup:
    """Клавиатура для просмотра статуса заявки"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Для заявок в статусе pending добавляем кнопку отмены
    if status == "pending":
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(
                text="❌ Отменить заявку",
                callback_data=f"cancel_application_{application_id}"
            )
        ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="🔄 Обновить статус",
            callback_data=f"refresh_application_{application_id}"
        )
    ])
    
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(
            text="◀️ Главное меню",
            callback_data="main_menu"
        )
    ])
    
    return keyboard


def get_moderator_photo_confirmation_keyboard(session_id: int) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения получения фото от модератора"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Получил подтверждение",
                callback_data=f"confirm_moderator_photo_{session_id}"
            )
        ]
    ])
    return keyboard


def get_applications_list_keyboard(applications: list) -> InlineKeyboardMarkup:
    """Клавиатура со списком заявок пользователя"""
    buttons = []
    for app in applications:
        status_emoji = {
            "pending": "⏳",
            "moderating": "🔄",
            "completed": "✅",
            "rejected": "❌",
            "cancelled": "🚫"
        }.get(app.status, "❓")
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{status_emoji} Заявка #{app.id} ({app.status})",
                callback_data=f"view_application_{app.id}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Главное меню",
            callback_data="main_menu"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
