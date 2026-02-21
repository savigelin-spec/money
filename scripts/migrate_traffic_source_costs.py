"""
Миграция: создание таблицы traffic_source_costs для хранения затрат по источникам трафика.
Запуск: python -m scripts.migrate_traffic_source_costs
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
            CREATE TABLE IF NOT EXISTS traffic_source_costs (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                source VARCHAR(64) NOT NULL,
                cost_rub REAL DEFAULT 0.0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
    print("Миграция traffic_source_costs завершена.")


if __name__ == "__main__":
    asyncio.run(migrate())
