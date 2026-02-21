"""
Миграция: таблицы traffic_channels и traffic_channel_sources для отчёта «По каналам».
Запуск: python -m scripts.migrate_traffic_channels
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
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS traffic_channels (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(64) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS traffic_channel_sources (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL REFERENCES traffic_channels(id) ON DELETE CASCADE,
                source VARCHAR(64) NOT NULL
            )
        """))
    print("Миграция traffic_channels завершена.")


if __name__ == "__main__":
    asyncio.run(migrate())
