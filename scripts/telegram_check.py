#!/usr/bin/env python3
"""Проверка Telegram-бота и доступа к каналу.

PYTHONPATH=. python3 scripts/telegram_check.py
PYTHONPATH=. python3 scripts/telegram_check.py @my_channel
"""

import asyncio
import sys

import httpx

from src.core.settings import settings
from src.services.publishers.telegram import TelegramPublisher


async def check_chat(client: httpx.AsyncClient, token: str, chat_id: str) -> None:
    response = await client.get(
        f"https://api.telegram.org/bot{token}/getChat",
        params={"chat_id": chat_id},
    )
    data = response.json()
    if data.get("ok"):
        chat = data["result"]
        print(f"  OK  {chat_id} → «{chat.get('title')}» (@{chat.get('username')})")
    else:
        print(f"  FAIL {chat_id} → {data.get('description')}")


async def main() -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        print("Задайте TELEGRAM_BOT_TOKEN в .env", file=sys.stderr)
        sys.exit(1)

    chat_id = sys.argv[1] if len(sys.argv) > 1 else TelegramPublisher()._chat_id()
    if not chat_id:
        print("Задайте TELEGRAM_CHANNEL_ID=@username в .env", file=sys.stderr)
        sys.exit(1)

    async with httpx.AsyncClient(timeout=20.0) as client:
        me = await client.get(f"https://api.telegram.org/bot{token}/getMe")
        me_data = me.json()
        if not me_data.get("ok"):
            print(f"Токен бота невалиден: {me_data.get('description')}", file=sys.stderr)
            sys.exit(1)
        bot = me_data["result"]
        print(f"Бот: @{bot['username']} ({bot['first_name']})")
        print(f"Проверка канала: {chat_id}")
        await check_chat(client, token, chat_id)

    print()
    print("Если FAIL «chat not found» для публичного канала:")
    print("  1. TELEGRAM_CHANNEL_ID=@username из ссылки t.me/username")
    print("  2. Бот добавлен админом канала с правом «Публикация сообщений»")


if __name__ == "__main__":
    asyncio.run(main())
