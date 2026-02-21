"""
Разовое: обнулить все активные сессии модерации.
Все сессии со статусом active → completed, связанные заявки → cancelled.
Запуск: python -m scripts.reset_active_sessions
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from database.db import get_session_maker
from database.queries import end_session_chat_only, get_application_by_id
from database.models import ModerationSession
from config import STATUS_CANCELLED


async def main():
    session_maker = get_session_maker()
    async with session_maker() as db_session:
        result = await db_session.execute(
            select(ModerationSession).where(ModerationSession.status == "active")
        )
        sessions = result.scalars().all()
        if not sessions:
            print("Активных сессий нет.")
            return

        for mod_session in sessions:
            await end_session_chat_only(db_session, mod_session)
            app = await get_application_by_id(db_session, mod_session.application_id)
            if app:
                app.status = STATUS_CANCELLED
            print(
                f"Сессия #{mod_session.id} (заявка #{mod_session.application_id}, "
                f"user={mod_session.user_id}, mod={mod_session.moderator_id}) -> завершена, заявка -> cancelled"
            )

        await db_session.commit()
        print(f"Готово. Обнулено сессий: {len(sessions)}.")


if __name__ == "__main__":
    asyncio.run(main())
