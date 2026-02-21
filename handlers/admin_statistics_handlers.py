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
    get_top_sources_report,
    get_channels_report,
    StatisticsPeriod,
    format_financial_stats,
    format_financial_all_time_block,
    format_applications_stats,
    format_users_stats,
    format_comprehensive_stats,
    format_traffic_stats,
    format_top_sources_report,
    format_channels_report,
    format_detailed_marketing_stats,
)
from utils.marketing import get_detailed_marketing_stats
from utils.user_messages import update_user_main_message
from keyboards.admin_keyboards import (
    get_statistics_main_keyboard,
    get_statistics_period_keyboard,
    get_statistics_type_keyboard,
    get_marketing_detail_keyboard,
    get_traffic_top_sources_keyboard,
    get_traffic_channels_keyboard,
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
    """Показать статистику за выбранный период (финансы с общими показателями или сводная)."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        period_key = callback.data.replace("stats_period_", "")
        period = _PERIOD_MAP.get(period_key, StatisticsPeriod.LAST_30_DAYS)
        data = await state.get_data()
        current_stats_type = data.get("current_stats_type")

        if current_stats_type == "financial":
            # Экран «Финансы»: период + общие показатели (всё время), без дублирования при period=all_time
            text = "Нет данных."
            async for session in get_session():
                period_stats = await get_financial_stats(session, period)
                text = format_financial_stats(period_stats)
                if period != StatisticsPeriod.ALL_TIME:
                    all_time_stats = await get_financial_stats(session, StatisticsPeriod.ALL_TIME)
                    text += format_financial_all_time_block(all_time_stats)
                await session.commit()
                break
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=text,
                reply_markup=get_statistics_period_keyboard(),
            )
            await callback.answer()
            answered = True
            return
        # Сводная статистика (как раньше)
        await state.clear()
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
    """Показать выбранный тип статистики. Для «Финансы» — период по умолчанию месяц + общие показатели + выбор периода."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        stats_type = callback.data.replace("stats_type_", "")
        period = StatisticsPeriod.LAST_30_DAYS
        text = "Нет данных."

        if stats_type == "financial":
            await state.update_data(current_stats_type="financial")
            async for session in get_session():
                period_stats = await get_financial_stats(session, period)
                all_time_stats = await get_financial_stats(session, StatisticsPeriod.ALL_TIME)
                await session.commit()
                text = format_financial_stats(period_stats) + format_financial_all_time_block(all_time_stats)
                break
            await update_user_main_message(
                bot=callback.bot,
                user_id=callback.from_user.id,
                text=text,
                reply_markup=get_statistics_period_keyboard(),
            )
            await callback.answer()
            answered = True
            return
        await state.clear()
        async for session in get_session():
            if stats_type == "applications":
                data = await get_applications_stats(session, period)
                text = format_applications_stats(data)
            elif stats_type == "users":
                data = await get_users_stats(session, period)
                text = format_users_stats(data)
            elif stats_type == "marketing":
                data = await get_detailed_marketing_stats(session)
                text = format_detailed_marketing_stats(data)
                await session.commit()
                await update_user_main_message(
                    bot=callback.bot,
                    user_id=callback.from_user.id,
                    text=text,
                    reply_markup=get_marketing_detail_keyboard(),
                )
                await callback.answer()
                answered = True
                return
            elif stats_type == "traffic":
                await state.update_data(
                    current_stats_type="traffic",
                    traffic_period=StatisticsPeriod.LAST_30_DAYS,
                    traffic_page=1,
                )
                report_data = await get_top_sources_report(
                    session, StatisticsPeriod.LAST_30_DAYS, page=1, per_page=3
                )
                text = format_top_sources_report(report_data)
                keyboard = get_traffic_top_sources_keyboard(
                    report_data["sources"],
                    report_data["page"],
                    report_data["total_pages"],
                )
                await update_user_main_message(
                    bot=callback.bot,
                    user_id=callback.from_user.id,
                    text=text,
                    reply_markup=keyboard,
                )
                await callback.answer()
                answered = True
                return
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


@router.callback_query(F.data.startswith("traffic_page_"))
async def callback_traffic_page(callback: CallbackQuery, state: FSMContext):
    """Пагинация отчёта «Топ источников»."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        page = int(callback.data.replace("traffic_page_", "").strip() or "1")
        data = await state.get_data()
        period = data.get("traffic_period", StatisticsPeriod.LAST_30_DAYS)
        text = "Нет данных."
        async for session in get_session():
            report_data = await get_top_sources_report(
                session, period, page=page, per_page=3
            )
            text = format_top_sources_report(report_data)
            keyboard = get_traffic_top_sources_keyboard(
                report_data["sources"],
                report_data["page"],
                report_data["total_pages"],
            )
            await session.commit()
            break
        await state.update_data(traffic_page=page)
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_traffic_page: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data == "traffic_top_refresh")
async def callback_traffic_top_refresh(callback: CallbackQuery, state: FSMContext):
    """Обновить отчёт «Топ источников»."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        data = await state.get_data()
        page = data.get("traffic_page", 1)
        period = data.get("traffic_period", StatisticsPeriod.LAST_30_DAYS)
        text = "Нет данных."
        async for session in get_session():
            report_data = await get_top_sources_report(
                session, period, page=page, per_page=3
            )
            text = format_top_sources_report(report_data)
            keyboard = get_traffic_top_sources_keyboard(
                report_data["sources"],
                report_data["page"],
                report_data["total_pages"],
            )
            await session.commit()
            break
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
        )
        await callback.answer("Обновлено.")
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_traffic_top_refresh: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data == "stats_marketing_refresh")
async def callback_stats_marketing_refresh(callback: CallbackQuery, state: FSMContext):
    """Обновить экран «Подробная статистика» (маркетинг)."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        text = "Нет данных."
        async for session in get_session():
            data = await get_detailed_marketing_stats(session)
            text = format_detailed_marketing_stats(data)
            await session.commit()
            break
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=get_marketing_detail_keyboard(),
        )
        await callback.answer("Обновлено.")
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_stats_marketing_refresh: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data == "traffic_top_by_channels")
async def callback_traffic_top_by_channels(callback: CallbackQuery, state: FSMContext):
    """Открыть отчёт «Статистика по каналам» (страница 1)."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        period = data.get("traffic_period", StatisticsPeriod.LAST_30_DAYS) if (data := await state.get_data()) else StatisticsPeriod.LAST_30_DAYS
        await state.update_data(traffic_view="channels", traffic_page=1)
        text = "Нет данных."
        async for session in get_session():
            report_data = await get_channels_report(session, period, page=1, per_page=3)
            text = format_channels_report(report_data)
            keyboard = get_traffic_channels_keyboard(
                report_data["channels"],
                report_data["page"],
                report_data["total_pages"],
            )
            await session.commit()
            break
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_traffic_top_by_channels: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data.startswith("traffic_channel_page_"))
async def callback_traffic_channel_page(callback: CallbackQuery, state: FSMContext):
    """Пагинация отчёта «По каналам»."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        page = int(callback.data.replace("traffic_channel_page_", "").strip() or "1")
        data = await state.get_data()
        period = data.get("traffic_period", StatisticsPeriod.LAST_30_DAYS)
        text = "Нет данных."
        async for session in get_session():
            report_data = await get_channels_report(session, period, page=page, per_page=3)
            text = format_channels_report(report_data)
            keyboard = get_traffic_channels_keyboard(
                report_data["channels"],
                report_data["page"],
                report_data["total_pages"],
            )
            await session.commit()
            break
        await state.update_data(traffic_page=page)
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_traffic_channel_page: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data == "traffic_channels_refresh")
async def callback_traffic_channels_refresh(callback: CallbackQuery, state: FSMContext):
    """Обновить отчёт «По каналам»."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        data = await state.get_data()
        page = data.get("traffic_page", 1)
        period = data.get("traffic_period", StatisticsPeriod.LAST_30_DAYS)
        text = "Нет данных."
        async for session in get_session():
            report_data = await get_channels_report(session, period, page=page, per_page=3)
            text = format_channels_report(report_data)
            keyboard = get_traffic_channels_keyboard(
                report_data["channels"],
                report_data["page"],
                report_data["total_pages"],
            )
            await session.commit()
            break
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
        )
        await callback.answer("Обновлено.")
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_traffic_channels_refresh: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data == "traffic_by_sources")
async def callback_traffic_by_sources(callback: CallbackQuery, state: FSMContext):
    """Переключение «По тегам» — вернуться к отчёту «Топ источников»."""
    answered = False
    try:
        if not await check_admin_access(callback):
            answered = True
            return
        await state.update_data(traffic_view="sources", traffic_page=1)
        period = (await state.get_data()).get("traffic_period", StatisticsPeriod.LAST_30_DAYS)
        text = "Нет данных."
        async for session in get_session():
            report_data = await get_top_sources_report(session, period, page=1, per_page=3)
            text = format_top_sources_report(report_data)
            keyboard = get_traffic_top_sources_keyboard(
                report_data["sources"],
                report_data["page"],
                report_data["total_pages"],
            )
            await session.commit()
            break
        await update_user_main_message(
            bot=callback.bot,
            user_id=callback.from_user.id,
            text=text,
            reply_markup=keyboard,
        )
        await callback.answer()
        answered = True
    except Exception as e:
        logger.exception("Ошибка в callback_traffic_by_sources: %s", e)
        raise
    finally:
        if not answered:
            try:
                await callback.answer()
            except Exception:
                pass


@router.callback_query(F.data.startswith("traffic_ch_"))
async def callback_traffic_channel_detail(callback: CallbackQuery, state: FSMContext):
    """Клик по каналу — пока только закрываем запрос."""
    await callback.answer()


@router.callback_query(F.data.startswith("traffic_src_"))
async def callback_traffic_source_detail(callback: CallbackQuery, state: FSMContext):
    """Клик по источнику — пока только закрываем запрос."""
    await callback.answer()


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
