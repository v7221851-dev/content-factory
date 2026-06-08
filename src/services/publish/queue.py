"""Очередь публикаций с интервалом между постами."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.settings import settings
from src.core.datetime_utils import ensure_utc
from src.models.entities import ArticleStatus, PublishPost, PublishStatus, RawArticle
from src.services.content.formatter import format_post
from src.services.publish.service import publish_text_to_platforms
from src.services.workflow.review import (
    get_article_or_none,
    validate_article_for_queue,
)


@dataclass
class QueueItemResult:
    article_id: int
    success: bool
    published_now: bool = False
    scheduled_at: datetime | None = None
    results: list | None = None
    error: str | None = None


@dataclass
class QueueBatchResult:
    items: list[QueueItemResult]
    published: int
    scheduled: int
    failed: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _interval() -> timedelta:
    return timedelta(minutes=settings.PUBLISH_INTERVAL_MINUTES)


def _initial_delay() -> timedelta:
    return timedelta(minutes=settings.PUBLISH_QUEUE_INITIAL_DELAY_MINUTES)


def _platforms_str(platforms: list[str]) -> str:
    return ",".join(platforms)


def _parse_platforms(value: str | None) -> list[str]:
    if not value:
        return settings.publish_platforms_list
    return [p.strip() for p in value.split(",") if p.strip()]


async def _last_publish_time(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(func.max(PublishPost.published_at)).where(
            PublishPost.status == PublishStatus.PUBLISHED,
            PublishPost.published_at.is_not(None),
        )
    )


async def _last_scheduled_slot(session: AsyncSession) -> datetime | None:
    return await session.scalar(
        select(func.max(RawArticle.scheduled_publish_at)).where(
            RawArticle.status == ArticleStatus.SCHEDULED,
            RawArticle.scheduled_publish_at.is_not(None),
        )
    )


async def next_queue_slot(session: AsyncSession) -> datetime:
    """Следующий слот очереди: не раньше now + PUBLISH_QUEUE_INITIAL_DELAY_MINUTES."""
    now = _now()
    min_slot = now + _initial_delay()

    if settings.PUBLISH_INTERVAL_MINUTES <= 0:
        return min_slot

    last_pub = ensure_utc(await _last_publish_time(session))
    last_sched = ensure_utc(await _last_scheduled_slot(session))

    anchor = max(
        (t for t in (last_pub, last_sched) if t is not None),
        default=None,
    )
    if anchor is None:
        return min_slot

    candidate = anchor + _interval()
    if candidate <= now:
        return max(now, min_slot)
    return max(candidate, min_slot)


async def publish_single_article(
    session: AsyncSession,
    article: RawArticle,
    platforms: list[str],
) -> QueueItemResult:
    if article.status == ArticleStatus.PUBLISHED:
        return QueueItemResult(
            article_id=article.id,
            success=False,
            error="уже опубликована",
        )

    if article.status == ArticleStatus.SCHEDULED:
        from src.services.workflow.review import get_published_content_hashes

        if article.content_hash in await get_published_content_hashes(session):
            return QueueItemResult(
                article_id=article.id,
                success=False,
                error="дубликат уже опубликованного материала",
            )
    else:
        ok, reason = await validate_article_for_queue(session, article)
        if not ok:
            return QueueItemResult(article_id=article.id, success=False, error=reason)

    text = format_post(
        title=article.title,
        summary=article.summary,
        source_url=article.url,
    )
    outcome = await publish_text_to_platforms(
        session=session,
        text=text,
        platforms=platforms,
        link=article.url,
        image_url=article.image_url,
        image_referer=article.url,
        article_id=article.id,
    )
    success = any(r.success for r in outcome.results)
    article.scheduled_publish_at = None
    article.scheduled_platforms = None
    return QueueItemResult(
        article_id=article.id,
        success=success,
        published_now=True,
        results=outcome.results,
        error=None if success else "all platforms failed",
    )


async def schedule_or_publish_batch(
    session: AsyncSession,
    article_ids: list[int],
    platforms: list[str],
) -> QueueBatchResult:
    """Ставит статьи в очередь публикации (первая — через initial delay, далее с интервалом)."""
    if settings.PUBLISH_INTERVAL_MINUTES <= 0:
        return await _publish_all_immediately(session, article_ids, platforms)

    sorted_ids = sorted(set(article_ids))
    platform_str = _platforms_str(platforms)
    items: list[QueueItemResult] = []
    published = scheduled = failed = 0
    next_slot = ensure_utc(await next_queue_slot(session)) or _now()

    for article_id in sorted_ids:
        article = await get_article_or_none(session, article_id)
        if article is None:
            items.append(QueueItemResult(article_id, False, error="Article not found"))
            failed += 1
            continue

        ok, reason = await validate_article_for_queue(session, article)
        if not ok:
            items.append(QueueItemResult(article_id, False, error=reason))
            failed += 1
            continue

        publish_at = ensure_utc(next_slot) or _now()
        article.status = ArticleStatus.SCHEDULED
        article.scheduled_publish_at = publish_at
        article.scheduled_platforms = platform_str
        await session.commit()
        items.append(
            QueueItemResult(
                article_id=article.id,
                success=True,
                published_now=False,
                scheduled_at=publish_at,
            )
        )
        scheduled += 1
        next_slot = publish_at + _interval()

    return QueueBatchResult(
        items=items,
        published=published,
        scheduled=scheduled,
        failed=failed,
    )


async def _publish_all_immediately(
    session: AsyncSession,
    article_ids: list[int],
    platforms: list[str],
) -> QueueBatchResult:
    items: list[QueueItemResult] = []
    published = failed = 0

    for article_id in article_ids:
        article = await get_article_or_none(session, article_id)
        if article is None:
            items.append(QueueItemResult(article_id, False, error="Article not found"))
            failed += 1
            continue

        ok, reason = await validate_article_for_queue(session, article)
        if not ok:
            items.append(QueueItemResult(article_id, False, error=reason))
            failed += 1
            continue

        item = await publish_single_article(session, article, platforms)
        items.append(item)
        if item.success:
            published += 1
        else:
            failed += 1

    return QueueBatchResult(
        items=items,
        published=published,
        scheduled=0,
        failed=failed,
    )


async def publish_due_scheduled(session: AsyncSession) -> int:
    """Публикует одну просроченную запланированную статью."""
    now = _now()
    result = await session.execute(
        select(RawArticle)
        .where(RawArticle.status == ArticleStatus.SCHEDULED)
        .where(RawArticle.scheduled_publish_at.is_not(None))
        .order_by(RawArticle.scheduled_publish_at.asc())
    )
    for article in result.scalars():
        due_at = ensure_utc(article.scheduled_publish_at)
        if due_at is None or due_at > now:
            continue

        if article.status == ArticleStatus.PUBLISHED:
            article.scheduled_publish_at = None
            article.scheduled_platforms = None
            await session.commit()
            continue

        platforms = _parse_platforms(article.scheduled_platforms)
        item = await publish_single_article(session, article, platforms)
        if not item.success:
            article.status = ArticleStatus.PENDING
            article.scheduled_publish_at = None
            article.scheduled_platforms = None
            await session.commit()
        return 1
    return 0
