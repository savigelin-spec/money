"""
Утилиты для работы с UTM-параметрами и источниками трафика.
"""
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


def parse_utm_params(text: str) -> dict[str, Any]:
    """
    Парсинг UTM-параметров из команды /start.

    Поддерживаемые форматы:
    - /start utm_source=telegram&utm_campaign=promo
    - /start?utm_source=telegram&utm_campaign=promo
    - /start ref123 (простой реферальный код)
    """
    params: dict[str, Any] = {}

    if not text or "/start" not in text:
        return params

    text = text.replace("/start", "").strip()
    if not text:
        return params

    if "?" in text or "&" in text or "=" in text:
        if text.startswith("?"):
            text = text[1:]
        pairs = text.split("&")
        for pair in pairs:
            if "=" in pair:
                key, value = pair.split("=", 1)
                key = key.strip().lower()
                if key.startswith("utm_"):
                    params[key[4:]] = value.strip()
                elif key == "ref":
                    params["source"] = f"ref_{value.strip()}"
    else:
        params["source"] = f"ref_{text.strip()}"

    return params


def normalize_traffic_source(params: dict[str, Any]) -> dict[str, Any]:
    """Нормализация параметров источника трафика."""
    normalized: dict[str, Any] = {
        "source": params.get("source", "direct"),
        "campaign": params.get("campaign"),
        "medium": params.get("medium"),
        "content": params.get("content"),
        "term": params.get("term"),
    }
    if normalized["source"]:
        normalized["source"] = str(normalized["source"]).lower().strip()
    return normalized


async def save_traffic_source(
    session: AsyncSession,
    user: User,
    params: dict[str, Any],
) -> None:
    """Сохранение источника трафика для пользователя."""
    normalized = normalize_traffic_source(params)
    user.traffic_source = normalized.get("source")
    user.traffic_campaign = normalized.get("campaign")
    user.traffic_medium = normalized.get("medium")
    user.traffic_content = normalized.get("content")
    user.traffic_term = normalized.get("term")
    await session.flush()
