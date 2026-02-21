"""
Скрипт для назначения администратора
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
from database.queries import get_or_create_user
from config import ROLE_ADMIN


async def set_admin():
    """Назначить администратора"""
    print("Инициализация базы данных...")
    await init_db()
    
    admin_id = 6341142035
    
    async for session in get_session():
        user = await get_or_create_user(session, user_id=admin_id)
        old_role = user.role
        user.role = ROLE_ADMIN
        await session.commit()
        
        print(f"[OK] Пользователь {admin_id} назначен администратором")
        print(f"     Предыдущая роль: {old_role}")
        print(f"     Новая роль: {user.role}")
        
        print("\n[OK] Операция выполнена успешно!")
        print(f"Теперь пользователь {admin_id} может использовать команду /admin")


if __name__ == "__main__":
    asyncio.run(set_admin())
