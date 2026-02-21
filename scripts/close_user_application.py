"""
Разовое: завершить активную заявку пользователя (чтобы мог создать новую).
Запуск: python -m scripts.close_user_application <user_id>
Пример: python -m scripts.close_user_application 1345405929
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from database.db import get_session_maker
from database.queries import end_session_chat_only, get_application_by_id, get_active_moderation_session_by_user
from database.models import Application
from config import STATUS_CANCELLED


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.close_user_application <user_id>")
        return
    user_id = int(sys.argv[1])

    session_maker = get_session_maker()
    async with session_maker() as db_session:
        # 1) Завершить активную сессию модерации пользователя
        mod_session = await get_active_moderation_session_by_user(db_session, user_id)
        if mod_session:
            await end_session_chat_only(db_session, mod_session)
            print(f"Session #{mod_session.id} (app #{mod_session.application_id}) -> completed")

        # 2) Все заявки пользователя pending/moderating -> cancelled
        result = await db_session.execute(
            select(Application).where(
                Application.user_id == user_id,
                Application.status.in_(["pending", "moderating"]),
            )
        )
        apps = result.scalars().all()
        for app in apps:
            app.status = STATUS_CANCELLED
            print(f"Application #{app.id} -> cancelled")

        await db_session.commit()
        if not mod_session and not apps:
            print("No active session or pending/moderating application found.")
        else:
            print("Done. User can create a new application.")


if __name__ == "__main__":
    asyncio.run(main())
