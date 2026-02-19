"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Стоимость заявки на подтверждение (в звёздах)
APPLICATION_COST = 300

# Среднее время сессии модератора по умолчанию (в секундах)
DEFAULT_MODERATOR_SESSION_TIME = 300  # 5 минут

# База данных
DATABASE_PATH = "bot_database.db"

# Роли пользователей
ROLE_USER = "user"
ROLE_MODERATOR = "moderator"
ROLE_ADMIN = "admin"

# Статусы заявок
STATUS_PENDING = "pending"
STATUS_MODERATING = "moderating"
STATUS_COMPLETED = "completed"
STATUS_REJECTED = "rejected"

# Статусы сессий модерации
SESSION_ACTIVE = "active"
SESSION_COMPLETED = "completed"

# Типы транзакций
TRANSACTION_DEPOSIT = "deposit"
TRANSACTION_WITHDRAWAL = "withdrawal"
