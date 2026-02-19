"""
Скрипт для пополнения баланса пользователя звёздами
"""
import asyncio
import sys
from pathlib import Path

# Настройка кодировки для Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import get_session
from database.queries import get_or_create_user, change_balance


async def add_stars_to_user(user_id: int, amount: int):
    """Пополнить баланс пользователя звёздами"""
    print(f"🔄 Пополнение баланса пользователя {user_id} на {amount}⭐...")
    
    async for session in get_session():
        try:
            user = await get_or_create_user(session, user_id=user_id)
            old_balance = user.balance
            
            await change_balance(
                session=session,
                user=user,
                amount=amount,
                description=f"Пополнение баланса администратором: +{amount}⭐",
                is_deposit=True
            )
            
            await session.refresh(user)
            await session.commit()
            
            print(f"✅ Успешно!")
            print(f"   Пользователь: {user_id}")
            print(f"   Было: {old_balance}⭐")
            print(f"   Добавлено: {amount}⭐")
            print(f"   Стало: {user.balance}⭐")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка: {e}")
            raise


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Использование: python scripts/add_stars.py <user_id> <amount>")
        print("Пример: python scripts/add_stars.py 8070278708 1000")
        sys.exit(1)
    
    try:
        user_id = int(sys.argv[1])
        amount = int(sys.argv[2])
        
        if amount <= 0:
            print("❌ Количество звёзд должно быть положительным числом")
            sys.exit(1)
        
        asyncio.run(add_stars_to_user(user_id, amount))
    except ValueError:
        print("❌ Неверный формат. user_id и amount должны быть целыми числами")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)
