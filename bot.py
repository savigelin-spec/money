"""
Главный файл Telegram бота для подтверждения возраста КСО
"""
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database.db import init_db
from handlers import user_handlers, moderator_handlers, admin_handlers, payment_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """
    Главная функция запуска бота
    """
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен! Создайте файл .env с BOT_TOKEN")
        return

    # Инициализация базы данных
    logger.info("Инициализация базы данных...")
    try:
        await init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")
        return

    # Инициализация бота и диспетчера
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Регистрация routers (важен порядок - более специфичные обработчики должны быть первыми)
    # ВАЖНО: Команда /start должна обрабатываться ПЕРВОЙ, независимо от состояния FSM
    dp.include_router(user_handlers.start_router)  # Команда /start обрабатывается первой
    dp.include_router(payment_handlers.router)  # Платежи должны обрабатываться первыми
    dp.include_router(moderator_handlers.router)  # Модератор
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)  # Пользователь в конце

    logger.info("Бот запущен...")
    
    try:
        # Запуск polling
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
