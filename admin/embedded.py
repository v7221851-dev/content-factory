"""Прямой доступ к сервисам без HTTP — для Streamlit Cloud."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

from src.core.db import async_session
from src.core.migrations import ensure_schema
from src.core.settings import settings
from src.models.entities import ArticleStatus
from src.services.content.formatter import format_post
from src.services.ingest.sources import (
    create_source as create_source_svc,
    delete_source as delete_source_svc,
    ensure_default_sources,
    ingest_one_source,
    list_sources as list_sources_svc,
    update_source as update_source_svc,
)
from src.services.ingest.rss import ingest_all_sources
from src.services.publish.queue import schedule_or_publish_batch
from src.services.publishers.registry import list_configured_platforms
from src.services.workflow.review import (
    build_preview,
    count_by_status,
    get_article_or_none,
    prepare_daily_review,
    reject_all_pending,
    reject_articles,
)
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from src.models.entities import ContentSource, RawArticle

_initialized = False


def _run(coro):
    return asyncio.run(coro)


async def _ensure_ready() -> None:
    global _initialized
    if _initialized:
        return
    await ensure_schema()
    async with async_session() as session:
        await ensure_default_sources(session)
    from src.core.scheduler import start_scheduler

    start_scheduler()
    _initialized = True


class EmbeddedBackend:
    """Тот же интерфейс, что ContentFactoryClient, но без HTTP."""

    def health(self) -> dict:
        _run(_ensure_ready())
        return {
            "status": "ok",
            "configured_platforms": list_configured_platforms(),
        }

    def stats(self) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                by_status = await count_by_status(session)
                return {
                    "by_status": by_status,
                    "pending_count": by_status.get(ArticleStatus.PENDING, 0),
                    "daily_review_limit": settings.DAILY_REVIEW_LIMIT,
                    "publish_interval_minutes": settings.PUBLISH_INTERVAL_MINUTES,
                    "configured_platforms": list_configured_platforms(),
                }

        return _run(_inner())

    def list_articles(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                query = (
                    select(RawArticle)
                    .options(selectinload(RawArticle.source))
                    .order_by(RawArticle.fetched_at.desc())
                )
                count_query = select(func.count()).select_from(RawArticle)

                if status:
                    query = query.where(RawArticle.status == status)
                    count_query = count_query.where(RawArticle.status == status)
                if source:
                    query = query.join(RawArticle.source).where(
                        ContentSource.name == source
                    )
                    count_query = count_query.join(RawArticle.source).where(
                        ContentSource.name == source
                    )
                if search:
                    pattern = f"%{search.strip()}%"
                    query = query.where(RawArticle.title.ilike(pattern))
                    count_query = count_query.where(RawArticle.title.ilike(pattern))

                total = await session.scalar(count_query) or 0
                result = await session.execute(query.limit(limit).offset(offset))
                articles = result.scalars().all()
                return {
                    "items": [
                        {
                            "id": a.id,
                            "title": a.title,
                            "url": a.url,
                            "summary": a.summary,
                            "image_url": a.image_url,
                            "status": a.status,
                            "fetched_at": a.fetched_at.isoformat(),
                            "source_name": a.source.name if a.source else None,
                            "scheduled_publish_at": (
                                a.scheduled_publish_at.isoformat()
                                if a.scheduled_publish_at
                                else None
                            ),
                        }
                        for a in articles
                    ],
                    "total": total,
                }

        return _run(_inner())

    def preview(self, article_id: int) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                article = await get_article_or_none(session, article_id)
                if article is None:
                    raise ValueError("Article not found")
                return {
                    "id": article.id,
                    "title": article.title,
                    "url": article.url,
                    "summary": article.summary,
                    "image_url": article.image_url,
                    "status": article.status,
                    "source_name": article.source.name if article.source else None,
                    "formatted_text": build_preview(article),
                }

        return _run(_inner())

    def ingest_rss(self) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                stats = await ingest_all_sources(session)
                sources = {
                    name: {
                        "fetched": r.fetched,
                        "new": r.new,
                        "skipped": r.skipped,
                        "error": r.error,
                    }
                    for name, r in stats.items()
                }
                return {
                    "sources": sources,
                    "total_new": sum(r.new for r in stats.values()),
                }

        return _run(_inner())

    def prepare_review(self, limit: int | None = None) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                result = await prepare_daily_review(session, limit=limit)
                return {
                    "selected": result.selected,
                    "already_pending": result.already_pending,
                    "available_new": result.available_new,
                }

        return _run(_inner())

    def publish_batch(
        self,
        article_ids: list[int],
        *,
        platforms: list[str] | None = None,
        reject_remaining: bool = False,
    ) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            resolved = platforms or settings.publish_platforms_list

            async with async_session() as session:
                batch = await schedule_or_publish_batch(
                    session,
                    article_ids,
                    resolved,
                )
                if reject_remaining:
                    await reject_all_pending(session)

            return {
                "items": [
                    {
                        "article_id": item.article_id,
                        "success": item.success,
                        "published_now": item.published_now,
                        "scheduled_at": (
                            item.scheduled_at.isoformat() if item.scheduled_at else None
                        ),
                        "results": (
                            [asdict(r) for r in item.results]
                            if item.results
                            else []
                        ),
                        "error": item.error,
                    }
                    for item in batch.items
                ],
                "published": batch.published,
                "scheduled": batch.scheduled,
                "failed": batch.failed,
            }

        return _run(_inner())

    def reject_articles(self, article_ids: list[int]) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                results = await reject_articles(session, article_ids)
                return {
                    "rejected": sum(1 for r in results if r.success),
                    "results": [
                        {
                            "article_id": r.article_id,
                            "success": r.success,
                            "detail": r.detail,
                        }
                        for r in results
                    ],
                }

        return _run(_inner())

    def reject_all_pending(self) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                count = await reject_all_pending(session)
                return {"rejected": count, "results": []}

        return _run(_inner())

    def _source_dict(self, item) -> dict:
        return {
            "id": item.id,
            "name": item.name,
            "feed_url": item.feed_url,
            "enabled": item.enabled,
            "last_fetched_at": (
                item.last_fetched_at.isoformat() if item.last_fetched_at else None
            ),
            "article_count": getattr(item, "article_count", 0),
        }

    def list_sources(self) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                items = await list_sources_svc(session)
                return {"items": [self._source_dict(i) for i in items]}

        return _run(_inner())

    def create_source(
        self,
        name: str,
        feed_url: str,
        *,
        enabled: bool = True,
        validate: bool = True,
    ) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                await create_source_svc(
                    session,
                    name,
                    feed_url,
                    enabled=enabled,
                    validate=validate,
                )
                items = await list_sources_svc(session)
                found = next((i for i in items if i.name == name.strip()), None)
                return self._source_dict(found) if found else {}

        return _run(_inner())

    def update_source(
        self,
        source_id: int,
        *,
        name: str | None = None,
        feed_url: str | None = None,
        enabled: bool | None = None,
        validate: bool = True,
    ) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                await update_source_svc(
                    session,
                    source_id,
                    name=name,
                    feed_url=feed_url,
                    enabled=enabled,
                    validate=validate,
                )
                items = await list_sources_svc(session)
                found = next((i for i in items if i.id == source_id), None)
                return self._source_dict(found) if found else {}

        return _run(_inner())

    def delete_source(self, source_id: int) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                await delete_source_svc(session, source_id)
                return {"ok": True}

        return _run(_inner())

    def ingest_source(self, source_id: int) -> dict:
        async def _inner() -> dict:
            await _ensure_ready()
            async with async_session() as session:
                result = await ingest_one_source(session, source_id)
                return {
                    "fetched": result.fetched,
                    "new": result.new,
                    "skipped": result.skipped,
                    "error": result.error,
                }

        return _run(_inner())
