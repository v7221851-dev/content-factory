#!/usr/bin/env python3
"""Опубликовать первые N статей из очереди (по id)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.core.db import async_session
from src.core.migrations import ensure_schema
from src.models.entities import ArticleStatus, PublishPost, PublishStatus, RawArticle
from src.services.content.formatter import format_post
from src.services.ingest.rss import ingest_all_sources
from src.services.publishers.registry import publish_to_platform


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", type=int, default=3, help="Сколько статей опубликовать")
    parser.add_argument("--status", default="new", help="Фильтр статуса")
    args = parser.parse_args()

    await ensure_schema()

    async with async_session() as session:
        print("Сбор RSS (обновление image_url)...")
        stats = await ingest_all_sources(session)
        for name, result in stats.items():
            print(f"  {name}: fetched={result.fetched}, new={result.new}, skipped={result.skipped}")

        query = (
            select(RawArticle)
            .options(selectinload(RawArticle.source))
            .where(RawArticle.status == args.status)
            .order_by(RawArticle.id.asc())
            .limit(args.n)
        )
        result = await session.execute(query)
        articles = result.scalars().all()

        if not articles:
            print("Нет статей для публикации")
            return 1

        ok = 0
        for article in articles:
            print(f"\n--- id={article.id} | {article.source.name if article.source else '?'} ---")
            print(f"title: {article.title[:80]}")
            print(f"image_url: {article.image_url or '(нет)'}")

            text = format_post(
                title=article.title,
                summary=article.summary,
                source_url=article.url,
            )
            outcome = await publish_to_platform(
                "vk",
                text,
                link=article.url,
                image_url=article.image_url,
            )

            post_status = PublishStatus.PUBLISHED if outcome.success else PublishStatus.FAILED
            session.add(
                PublishPost(
                    article_id=article.id,
                    platform="vk",
                    text=text,
                    status=post_status,
                    external_id=outcome.external_id,
                    error_message=outcome.error,
                    published_at=datetime.now(timezone.utc) if outcome.success else None,
                )
            )

            if outcome.success:
                article.status = ArticleStatus.PUBLISHED
                ok += 1
                print(f"OK: {outcome.post_url}")
            else:
                print(f"ERROR: {outcome.error}")

        await session.commit()
        print(f"\nИтого: {ok}/{len(articles)} опубликовано")
        return 0 if ok == len(articles) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
