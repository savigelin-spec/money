"""
Миграция: добавление полей UTM/трафика в users и создание таблицы traffic_sources.
Запуск: python -m scripts.migrate_add_traffic_tracking
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.db import get_engine


async def migrate():
    engine = get_engine()
    async with engine.begin() as conn:
        # Таблица traffic_sources — создаётся через create_all при init_db,
        # но на случай ручного запуска миграции создаём через SQL
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS traffic_sources (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                source VARCHAR(64) NOT NULL,
                campaign VARCHAR(64),
                medium VARCHAR(64),
                content VARCHAR(64),
                term VARCHAR(64),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Таблица moderator_stats (для статистики модератора)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS moderator_stats (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                moderator_id INTEGER NOT NULL REFERENCES users(user_id),
                total_sessions INTEGER DEFAULT 0,
                total_time_seconds INTEGER DEFAULT 0,
                average_session_time REAL DEFAULT 0.0,
                UNIQUE (moderator_id)
            )
        """))
        # Добавление столбцов в users (SQLite не поддерживает IF NOT EXISTS для столбцов)
        columns = [
            ("main_message_id", "INTEGER"),
            ("traffic_source", "VARCHAR(64)"),
            ("traffic_campaign", "VARCHAR(64)"),
            ("traffic_medium", "VARCHAR(64)"),
            ("traffic_content", "VARCHAR(64)"),
            ("traffic_term", "VARCHAR(64)"),
            ("referrer_user_id", "INTEGER"),
            ("first_action_at", "DATETIME"),
            ("first_deposit_at", "DATETIME"),
            ("first_application_at", "DATETIME"),
        ]
        for col_name, col_type in columns:
            try:
                await conn.execute(
                    text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                )
                print(f"  + users.{col_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print(f"  (users.{col_name} уже есть)")
                else:
                    raise
        # moderation_sessions: колонки для сообщений (если таблица уже была без них)
        mod_columns = [
            ("user_main_message_id", "INTEGER"),
            ("user_info_message_id", "INTEGER"),
        ]
        for col_name, col_type in mod_columns:
            try:
                await conn.execute(
                    text(f"ALTER TABLE moderation_sessions ADD COLUMN {col_name} {col_type}")
                )
                print(f"  + moderation_sessions.{col_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print(f"  (moderation_sessions.{col_name} уже есть)")
                else:
                    raise
    print("Миграция завершена.")


if __name__ == "__main__":
    asyncio.run(migrate())
