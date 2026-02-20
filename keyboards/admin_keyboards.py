"""
Клавиатуры для панели администратора и статистики.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура панели администратора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_statistics")],
    ])


def get_statistics_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню статистики."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Финансы", callback_data="stats_type_financial")],
        [InlineKeyboardButton(text="📋 Заявки", callback_data="stats_type_applications")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="stats_type_users")],
        [InlineKeyboardButton(text="📈 Маркетинг", callback_data="stats_type_marketing")],
        [InlineKeyboardButton(text="🔗 Источники трафика", callback_data="stats_type_traffic")],
        [InlineKeyboardButton(text="📋 Всё вместе", callback_data="stats_type_comprehensive")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel_back")],
    ])


def get_statistics_period_keyboard() -> InlineKeyboardMarkup:
    """Выбор периода статистики."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня", callback_data="stats_period_today"),
            InlineKeyboardButton(text="7 дней", callback_data="stats_period_7_days"),
        ],
        [
            InlineKeyboardButton(text="30 дней", callback_data="stats_period_30_days"),
            InlineKeyboardButton(text="Всё время", callback_data="stats_period_all_time"),
        ],
        [InlineKeyboardButton(text="◀️ К статистике", callback_data="admin_statistics")],
    ])


def get_statistics_type_keyboard() -> InlineKeyboardMarkup:
    """Выбор типа статистики (после просмотра)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data="stats_type_financial"),
            InlineKeyboardButton(text="📋 Заявки", callback_data="stats_type_applications"),
        ],
        [
            InlineKeyboardButton(text="👥 Пользователи", callback_data="stats_type_users"),
            InlineKeyboardButton(text="📈 Маркетинг", callback_data="stats_type_marketing"),
        ],
        [InlineKeyboardButton(text="🔗 Трафик", callback_data="stats_type_traffic")],
        [InlineKeyboardButton(text="◀️ К статистике", callback_data="admin_statistics")],
    ])
