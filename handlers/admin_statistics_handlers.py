"""
Обработчики статистики для администраторов.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery

from database.db import get_session
from utils.statistics import (
    get_comprehensive_stats,
    get_financial_stats,
    get_applications_stats,
    get_users_stats,
    get_traffic_stats,
    StatisticsPeriod,
    format_financial_stats,
    format_applications_stats,
    format_users_stats,
    format_comprehensive_stats,
    format_traffic_stats,
    format_marketing_stats,
)
from utils.marketing import (
    get_conversion_funnel,
    get_average_ltv,
    get_retention_rate,
)
from utils.telegram_helpers import safe_edit_message_text
from utils.admin_messages import update_admin_message
from keyboards.admin_keyboards import (
    get_statistics_main_keyboard,
    get_statistics_period_keyboard,
    get_statistics_type_keyboard,
    get_admin_panel_keyboard,
)
from handlers.admin_handlers import check_admin_access

logger = logging.getLogger(__name__)
router = Router()

_PERIOD_MAP = {
    "today": StatisticsPeriod.TODAY,
    "7_days": StatisticsPeriod.LAST_7_DAYS,
    "30_days": StatisticsPeriod.LAST_30_DAYS,
    "all_time": StatisticsPeriod.ALL_TIME,
}


@router.callback_query(F.data == "admin_statistics")
async def callback_admin_statistics(callback: CallbackQuery):
    """Главная страница статистики."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        text = "📊 Статистика бота\n\nВыберите раздел:"
        await update_admin_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_statistics_main_keyboard(),
            message_id=callback.message.message_id if callback.message else None,
            chat_id=callback.message.chat.id if callback.message else None,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_admin_statistics: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data.startswith("stats_period_"))
async def callback_stats_period(callback: CallbackQuery):
    """Показать сводную статистику за выбранный период."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        period_key = callback.data.replace("stats_period_", "")
        period = _PERIOD_MAP.get(period_key, StatisticsPeriod.LAST_30_DAYS)
        text = "Нет данных."
        async for session in get_session():
            stats = await get_comprehensive_stats(session, period)
            await session.commit()
            text = format_comprehensive_stats(stats)
            break
        await update_admin_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_statistics_period_keyboard(),
            message_id=callback.message.message_id if callback.message else None,
            chat_id=callback.message.chat.id if callback.message else None,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_stats_period: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data.startswith("stats_type_"))
async def callback_stats_type(callback: CallbackQuery):
    """Показать выбранный тип статистики (период по умолчанию 30 дней)."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        stats_type = callback.data.replace("stats_type_", "")
        period = StatisticsPeriod.LAST_30_DAYS
        text = "Нет данных."
        async for session in get_session():
            if stats_type == "financial":
                data = await get_financial_stats(session, period)
                text = format_financial_stats(data)
            elif stats_type == "applications":
                data = await get_applications_stats(session, period)
                text = format_applications_stats(data)
            elif stats_type == "users":
                data = await get_users_stats(session, period)
                text = format_users_stats(data)
            elif stats_type == "marketing":
                funnel = await get_conversion_funnel(session)
                ltv = await get_average_ltv(session)
                retention = await get_retention_rate(session)
                text = format_marketing_stats(funnel, ltv, retention)
            elif stats_type == "traffic":
                data = await get_traffic_stats(session, period)
                text = format_traffic_stats(data)
            elif stats_type == "comprehensive":
                data = await get_comprehensive_stats(session, period)
                text = format_comprehensive_stats(data)
            await session.commit()
            break
        await update_admin_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_statistics_type_keyboard(),
            message_id=callback.message.message_id if callback.message else None,
            chat_id=callback.message.chat.id if callback.message else None,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_stats_type: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data == "admin_panel_back")
async def callback_admin_panel_back(callback: CallbackQuery):
    """Возврат к панели администратора (текст + кнопка Статистика)."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        from keyboards.admin_keyboards import get_admin_panel_keyboard
        text = (
            "👑 Панель администратора\n\n"
            "Доступные команды:\n"
            "/set_role &lt;user_id&gt; &lt;role&gt; — назначить роль\n"
            "/list_users — список пользователей\n"
            "/user_info &lt;user_id&gt; — информация о пользователе\n"
            "/set_moderator &lt;user_id&gt; — назначить модератора\n"
            "/remove_moderator &lt;user_id&gt; — снять модератора\n\n"
            "Роли: user, moderator, admin"
        )
        await update_admin_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_admin_panel_keyboard(),
            message_id=callback.message.message_id if callback.message else None,
            chat_id=callback.message.chat.id if callback.message else None,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_admin_panel_back: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass
