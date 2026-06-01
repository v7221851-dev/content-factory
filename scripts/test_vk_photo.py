#!/usr/bin/env python3
"""Диагностика: скачивание картинки и загрузка в VK."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy import select

from src.core.db import async_session
from src.core.migrations import ensure_schema
from src.core.settings import settings
from src.models.entities import RawArticle
from src.services.publishers.vk import VKPublisher, USER_AGENT

TEST_IMAGE = (
    "https://n1s1.hsmedia.ru/40/a8/75/40a875423bc4bf70e4366d09bc641eaf/"
    "1254x836_0xHbZMmeeE_4079350668053995470.jpg"
)
REFERER = "https://doctorpiter.ru/"


async def main() -> int:
    await ensure_schema()

    async with async_session() as session:
        for aid in (105, 106, 107):
            article = await session.get(RawArticle, aid)
            if article:
                print(f"id={aid} image_url={article.image_url!r}")

    print("\n--- download test ---")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for label, headers in [
            ("no referer", {"User-Agent": USER_AGENT}),
            ("with referer", {"User-Agent": USER_AGENT, "Referer": REFERER}),
        ]:
            r = await client.get(TEST_IMAGE, headers=headers)
            ct = r.headers.get("content-type", "")
            print(f"{label}: status={r.status_code} type={ct} bytes={len(r.content)}")

        print("\n--- VK upload test ---")
        if not settings.VK_USER_ACCESS_TOKEN:
            print("VK_USER_ACCESS_TOKEN не задан — загрузка фото невозможна")
            print("Добавьте ключ пользователя-админа в content-factory/.env")
            return 1

        publisher = VKPublisher()
        attachment = await publisher._upload_wall_photo(
            client,
            image_url=TEST_IMAGE,
            group_id=settings.VK_GROUP_ID or "",
            referer=REFERER,
        )
        print(f"attachment={attachment[0]!r} error={attachment[1]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
