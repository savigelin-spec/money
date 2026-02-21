"""
Обработчики статистики для администраторов.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

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
from utils.user_messages import update_user_main_message
from keyboards.admin_keyboards import (
    get_statistics_main_keyboard,
    get_statistics_period_keyboard,
    get_statistics_type_keyboard,
    get_admin_back_keyboard,
)
from handlers.admin_handlers import check_admin_access, ADMIN_PANEL_TITLE

logger = logging.getLogger(__name__)
router = Router()

_PERIOD_MAP = {
    "today": StatisticsPeriod.TODAY,
    "7_days": StatisticsPeriod.LAST_7_DAYS,
    "30_days": StatisticsPeriod.LAST_30_DAYS,
    "all_time": StatisticsPeriod.ALL_TIME,
}


@router.callback_query(F.data == "admin_statistics")
async def callback_admin_statistics(callback: CallbackQuery, state: FSMContext):
    """Главная страница статистики."""
    await state.clear()
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        text = "📊 Статистика бота\n\nВыберите раздел:"
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_statistics_main_keyboard(),
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
async def callback_stats_period(callback: CallbackQuery, state: FSMContext):
    """Показать сводную статистику за выбранный период."""
    await state.clear()
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
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_statistics_period_keyboard(),
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
async def callback_stats_type(callback: CallbackQuery, state: FSMContext):
    """Показать выбранный тип статистики (период по умолчанию 30 дней)."""
    await state.clear()
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
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_statistics_type_keyboard(),
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
async def callback_admin_panel_back(callback: CallbackQuery, state: FSMContext):
    """Возврат к панели администратора."""
    await state.clear()
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        from keyboards.admin_keyboards import get_admin_panel_keyboard
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=ADMIN_PANEL_TITLE,
            reply_markup=get_admin_panel_keyboard(),
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


@router.callback_query(F.data == "admin_stats_block10")
async def callback_admin_stats_block10(callback: CallbackQuery, state: FSMContext):
    """Заглушка: Блок 10 — в разработке."""
    await state.clear()
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        text = "📦 Блок 10 — в разработке.\n\nРаздел будет добавлен в следующих версиях."
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀️ К статистике", callback_data="admin_statistics")],
            ]),
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_admin_stats_block10: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass
