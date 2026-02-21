"""
Клавиатуры для панели администратора и статистики.
"""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_panel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура панели администратора."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_statistics")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users")],
        [InlineKeyboardButton(text="👤 Инфо о пользователе", callback_data="admin_user_info")],
        [
            InlineKeyboardButton(text="✏️ Назначить роль", callback_data="admin_set_role"),
            InlineKeyboardButton(text="➕ Модератор", callback_data="admin_set_moderator"),
        ],
        [InlineKeyboardButton(text="➖ Снять модератора", callback_data="admin_remove_moderator")],
        [
            InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin_settings"),
        ],
        [InlineKeyboardButton(text="📜 Лог действий", callback_data="admin_actions_log")],
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu")],
    ])


def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура «Назад» в панель админа (для подстраниц)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel_back")],
    ])


def get_admin_role_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора роли (user / moderator / admin)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="user", callback_data="admin_role_user"),
            InlineKeyboardButton(text="moderator", callback_data="admin_role_moderator"),
            InlineKeyboardButton(text="admin", callback_data="admin_role_admin"),
        ],
        [InlineKeyboardButton(text="◀️ Отмена", callback_data="admin_panel_back")],
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
        [InlineKeyboardButton(text="📦 Блок 10 (в разработке)", callback_data="admin_stats_block10")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel_back")],
    ])


def get_statistics_period_keyboard() -> InlineKeyboardMarkup:
    """Выбор периода статистики (День / Неделя / Месяц / Общие)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="День", callback_data="stats_period_today"),
            InlineKeyboardButton(text="Неделя", callback_data="stats_period_7_days"),
        ],
        [
            InlineKeyboardButton(text="Месяц", callback_data="stats_period_30_days"),
            InlineKeyboardButton(text="Общие", callback_data="stats_period_all_time"),
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
