"""
Разовое: обнулить активную заявку пользователю 8070278708, выдать 5000 звёзд пользователю 1345405929.
Запуск: python -m scripts.oneoff_fix_users
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database.db import get_session_maker
from database.queries import (
    get_or_create_user,
    change_balance,
)
from database.models import Application
from sqlalchemy import select


async def main():
    session_maker = get_session_maker()
    async with session_maker() as session:
        # 1) 8070278708 — обнулить активную заявку (pending/moderating -> cancelled)
        user_id_reset = 8070278708
        result = await session.execute(
            select(Application).where(
                Application.user_id == user_id_reset,
                Application.status.in_(["pending", "moderating"]),
            )
        )
        apps = result.scalars().all()
        for app in apps:
            app.status = "cancelled"
            print(f"Заявка #{app.id} пользователя {user_id_reset} переведена в cancelled")
        if not apps:
            print(f"У пользователя {user_id_reset} не найдено активных заявок (pending/moderating)")

        # 2) 1345405929 — выдать 5000 звёзд
        user_id_stars = 1345405929
        user = await get_or_create_user(session, user_id=user_id_stars)
        await change_balance(
            session=session,
            user=user,
            amount=5000,
            description="Выдача 5000 звёзд (разово)",
            is_deposit=True,
        )
        await session.flush()
        print(f"Пользователю {user_id_stars} начислено 5000 звёзд. Баланс: {user.balance}")

        await session.commit()
    print("Готово.")


if __name__ == "__main__":
    asyncio.run(main())
