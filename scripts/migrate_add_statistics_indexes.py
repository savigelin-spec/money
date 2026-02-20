"""
Миграция: добавление индексов для ускорения запросов статистики.
Запуск: python -m scripts.migrate_add_statistics_indexes
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.db import get_engine


async def add_indexes():
    """Создание индексов (IF NOT EXISTS для SQLite 3.40+ или игнор ошибок)."""
    engine = get_engine()
    async with engine.begin() as conn:
        indexes = [
            ("idx_user_traffic_source", "users", "traffic_source"),
            ("idx_user_traffic_campaign", "users", "traffic_campaign"),
            ("idx_user_created_at", "users", "created_at"),
            ("idx_user_first_deposit_at", "users", "first_deposit_at"),
            ("idx_user_first_application_at", "users", "first_application_at"),
            ("idx_transaction_user_id", "transactions", "user_id"),
            ("idx_transaction_type", "transactions", "type"),
            ("idx_transaction_created_at", "transactions", "created_at"),
            ("idx_transaction_user_type", "transactions", "user_id, type"),
            ("idx_application_user_id", "applications", "user_id"),
            ("idx_application_status", "applications", "status"),
            ("idx_application_created_at", "applications", "created_at"),
            ("idx_application_started_at", "applications", "started_at"),
            ("idx_application_completed_at", "applications", "completed_at"),
        ]
        for name, table, columns in indexes:
            try:
                await conn.execute(
                    text(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})")
                )
                print(f"  + {name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"  (индекс {name} уже есть)")
                else:
                    raise
    print("Индексы добавлены.")


if __name__ == "__main__":
    asyncio.run(add_indexes())
