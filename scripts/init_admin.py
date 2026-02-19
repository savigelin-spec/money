"""
Скрипт для инициализации администратора и настройки пользователей
"""
import asyncio
import sys
from pathlib import Path

# Настройка кодировки для Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import get_session, init_db
from database.queries import get_or_create_user, change_balance
from config import ROLE_MODERATOR, ROLE_ADMIN


async def setup_users():
    """Настройка пользователей"""
    print("Инициализация базы данных...")
    await init_db()
    
    async for session in get_session():
        # 1. Назначить модератора (6341142035)
        moderator_id = 6341142035
        moderator = await get_or_create_user(session, user_id=moderator_id)
        moderator.role = ROLE_MODERATOR
        print(f"[OK] Пользователь {moderator_id} назначен модератором")
        
        # 2. Пополнить баланс (1345405929) на 1000 звёзд
        user_id = 1345405929
        user = await get_or_create_user(session, user_id=user_id)
        await change_balance(
            session=session,
            user=user,
            amount=1000,
            description="Начальное пополнение баланса",
            is_deposit=True
        )
        await session.refresh(user)
        print(f"[OK] Пользователю {user_id} добавлено 1000⭐ на баланс. Новый баланс: {user.balance}⭐")
        
        await session.commit()
        print("\n[OK] Все операции выполнены успешно!")


if __name__ == "__main__":
    asyncio.run(setup_users())
