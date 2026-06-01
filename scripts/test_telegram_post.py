#!/usr/bin/env python3
"""Тест публикации в Telegram. Запуск из content-factory:

PYTHONPATH=. python3 scripts/test_telegram_post.py
PYTHONPATH=. python3 scripts/test_telegram_post.py --with-photo
"""

import argparse
import asyncio
import sys

from src.services.publishers.telegram import TelegramPublisher


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test Telegram publish")
    parser.add_argument(
        "--with-photo",
        action="store_true",
        help="Отправить тестовое фото (placeholder)",
    )
    args = parser.parse_args()

    publisher = TelegramPublisher()
    if not publisher.is_configured():
        print(
            "Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHANNEL_ID в content-factory/.env",
            file=sys.stderr,
        )
        sys.exit(1)

    text = (
        "🧪 Тест content-factory\n\n"
        "Если вы видите это сообщение — Telegram publisher работает."
    )
    image_url = None
    if args.with_photo:
        image_url = "https://picsum.photos/800/600"

    result = await publisher.publish(text=text, image_url=image_url)
    if result.success:
        print(f"OK: {result.post_url or result.external_id}")
        if result.warning:
            print(f"Warning: {result.warning}")
    else:
        print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
