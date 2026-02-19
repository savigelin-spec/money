"""
Скрипт миграции для конвертации балансов и транзакций из float в int (рубли -> звёзды).

Выполняет округление всех существующих балансов и сумм транзакций до целых чисел.
Конвертация: 1₽ = 1⭐ (просто округление до целого числа).
"""
import asyncio
import sys
from pathlib import Path

# Настройка кодировки для Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корневую директорию в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, text
from database.db import get_session
from database.models import User, Transaction


async def migrate_to_stars():
    """Миграция балансов и транзакций из float в int"""
    print("🔄 Начало миграции на систему звёзд...")
    
    async for session in get_session():
        try:
            # 1. Конвертация балансов пользователей через SQL UPDATE
            print("\n1. Конвертация балансов пользователей...")
            # Используем SQL для гарантированного обновления всех записей
            await session.execute(
                text("UPDATE users SET balance = CAST(ROUND(balance) AS INTEGER)")
            )
            await session.flush()
            
            # Проверяем результаты
            result = await session.execute(select(User))
            users = result.scalars().all()
            print(f"   ✅ Обработано пользователей: {len(users)}")
            for user in users[:10]:  # Показываем первые 10
                print(f"   Пользователь {user.user_id}: баланс {user.balance}⭐")
            if len(users) > 10:
                print(f"   ... и ещё {len(users) - 10} пользователей")
            
            # 2. Конвертация сумм транзакций через SQL UPDATE
            print("\n2. Конвертация сумм транзакций...")
            await session.execute(
                text("UPDATE transactions SET amount = CAST(ROUND(amount) AS INTEGER)")
            )
            await session.flush()
            
            # Проверяем результаты
            result = await session.execute(select(Transaction))
            transactions = result.scalars().all()
            print(f"   ✅ Обработано транзакций: {len(transactions)}")
            for transaction in transactions[:10]:  # Показываем первые 10
                print(f"   Транзакция #{transaction.id}: сумма {transaction.amount}⭐")
            if len(transactions) > 10:
                print(f"   ... и ещё {len(transactions) - 10} транзакций")
            
            # 3. Коммит изменений
            await session.commit()
            print("\n✅ Миграция завершена успешно!")
            print(f"   Всего обработано: {len(users)} пользователей, {len(transactions)} транзакций")
            print("\n⚠️  ВАЖНО: Если в БД были колонки типа REAL, может потребоваться")
            print("   пересоздание таблиц. Проверьте работу приложения после миграции.")
            
        except Exception as e:
            await session.rollback()
            print(f"\n❌ Ошибка при миграции: {e}")
            print("\n💡 Если ошибка связана с типами колонок, может потребоваться")
            print("   пересоздать таблицы через init_db() после резервного копирования данных.")
            raise


if __name__ == "__main__":
    asyncio.run(migrate_to_stars())
