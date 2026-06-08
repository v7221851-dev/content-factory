from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.settings import settings
from src.models.entities import (
    ArticleStatus,
    ContentSource,
    PublishPost,
    PublishStatus,
    RawArticle,
)
from src.services.content.formatter import format_post


@dataclass
class PrepareReviewResult:
    selected: int
    already_pending: int
    available_new: int


@dataclass
class BatchActionResult:
    article_id: int
    success: bool
    detail: str | None = None


@dataclass
class PublishedArticleSummary:
    id: int
    title: str
    url: str
    source_name: str | None
    published_at: datetime
    content_hash: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_published_content_hashes(session: AsyncSession) -> set[str]:
    rows = await session.execute(
        select(RawArticle.content_hash)
        .where(RawArticle.status == ArticleStatus.PUBLISHED)
        .distinct()
    )
    return set(rows.scalars().all())


async def get_scheduled_content_hashes(session: AsyncSession) -> set[str]:
    rows = await session.execute(
        select(RawArticle.content_hash)
        .where(RawArticle.status == ArticleStatus.SCHEDULED)
        .distinct()
    )
    return set(rows.scalars().all())


async def validate_article_for_queue(
    session: AsyncSession,
    article: RawArticle,
) -> tuple[bool, str | None]:
    """Проверка перед постановкой в очередь или публикацией."""
    if article.status == ArticleStatus.PUBLISHED:
        return False, "уже опубликована"

    if article.status == ArticleStatus.SCHEDULED:
        return False, "уже в очереди публикации"

    if article.status not in (
        ArticleStatus.PENDING,
        ArticleStatus.NEW,
        ArticleStatus.READY,
    ):
        return False, f"статус {article.status}"

    published_hashes = await get_published_content_hashes(session)
    if article.content_hash in published_hashes:
        return False, "дубликат уже опубликованного материала"

    scheduled_hashes = await get_scheduled_content_hashes(session)
    if article.content_hash in scheduled_hashes:
        return False, "похожий материал уже в очереди"

    return True, None


def _new_from_enabled_sources_query():
    """Статьи new только из включённых RSS-источников."""
    return (
        select(RawArticle)
        .join(RawArticle.source)
        .where(RawArticle.status == ArticleStatus.NEW)
        .where(ContentSource.enabled.is_(True))
    )


async def _count_new_from_enabled_sources(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(RawArticle)
            .join(RawArticle.source)
            .where(RawArticle.status == ArticleStatus.NEW)
            .where(ContentSource.enabled.is_(True))
        )
        or 0
    )


async def count_by_status(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(
        select(RawArticle.status, func.count())
        .group_by(RawArticle.status)
    )
    return {status: count for status, count in rows.all()}


async def prepare_daily_review(
    session: AsyncSession,
    limit: int | None = None,
) -> PrepareReviewResult:
    """Переносит N свежих статей из new → pending для согласования."""
    batch_size = limit or settings.DAILY_REVIEW_LIMIT

    pending_count = await session.scalar(
        select(func.count())
        .select_from(RawArticle)
        .where(RawArticle.status == ArticleStatus.PENDING)
    ) or 0

    if pending_count >= batch_size:
        new_count = await _count_new_from_enabled_sources(session)
        return PrepareReviewResult(
            selected=0,
            already_pending=pending_count,
            available_new=new_count,
        )

    slots = batch_size - pending_count
    published_hashes = await get_published_content_hashes(session)

    query = (
        _new_from_enabled_sources_query()
        .order_by(RawArticle.fetched_at.desc())
        .limit(slots)
    )
    if published_hashes:
        query = query.where(RawArticle.content_hash.notin_(published_hashes))

    result = await session.execute(query)
    articles = result.scalars().all()

    for article in articles:
        article.status = ArticleStatus.PENDING

    await session.commit()

    new_count = await _count_new_from_enabled_sources(session)

    return PrepareReviewResult(
        selected=len(articles),
        already_pending=pending_count,
        available_new=new_count,
    )


async def reject_articles(
    session: AsyncSession,
    article_ids: list[int],
) -> list[BatchActionResult]:
    results: list[BatchActionResult] = []
    for article_id in article_ids:
        article = await session.get(RawArticle, article_id)
        if article is None:
            results.append(BatchActionResult(article_id, False, "not found"))
            continue
        if article.status not in (
            ArticleStatus.PENDING,
            ArticleStatus.NEW,
            ArticleStatus.READY,
            ArticleStatus.SCHEDULED,
        ):
            results.append(
                BatchActionResult(
                    article_id,
                    False,
                    f"нельзя отклонить статус {article.status}",
                )
            )
            continue
        article.status = ArticleStatus.SKIPPED
        article.scheduled_publish_at = None
        article.scheduled_platforms = None
        results.append(BatchActionResult(article_id, True))
    await session.commit()
    return results


async def cancel_scheduled_articles(
    session: AsyncSession,
    article_ids: list[int],
) -> list[BatchActionResult]:
    """Убирает статьи из очереди публикации обратно на согласование."""
    results: list[BatchActionResult] = []
    for article_id in article_ids:
        article = await session.get(RawArticle, article_id)
        if article is None:
            results.append(BatchActionResult(article_id, False, "not found"))
            continue
        if article.status != ArticleStatus.SCHEDULED:
            results.append(
                BatchActionResult(
                    article_id,
                    False,
                    f"не в очереди (статус {article.status})",
                )
            )
            continue
        article.status = ArticleStatus.PENDING
        article.scheduled_publish_at = None
        article.scheduled_platforms = None
        results.append(BatchActionResult(article_id, True))
    await session.commit()
    return results


async def reject_all_pending(session: AsyncSession) -> int:
    result = await session.execute(
        select(RawArticle).where(RawArticle.status == ArticleStatus.PENDING)
    )
    articles = result.scalars().all()
    for article in articles:
        article.status = ArticleStatus.SKIPPED
    await session.commit()
    return len(articles)


async def list_recently_published(
    session: AsyncSession,
    *,
    days: int = 7,
    limit: int = 50,
) -> list[PublishedArticleSummary]:
    since = _now() - timedelta(days=days)
    result = await session.execute(
        select(
            RawArticle,
            func.max(PublishPost.published_at).label("last_published"),
        )
        .join(PublishPost, PublishPost.article_id == RawArticle.id)
        .options(selectinload(RawArticle.source))
        .where(PublishPost.status == PublishStatus.PUBLISHED)
        .where(PublishPost.published_at.is_not(None))
        .where(PublishPost.published_at >= since)
        .group_by(RawArticle.id)
        .order_by(func.max(PublishPost.published_at).desc())
        .limit(limit)
    )
    items: list[PublishedArticleSummary] = []
    for article, published_at in result.all():
        if published_at is None:
            continue
        items.append(
            PublishedArticleSummary(
                id=article.id,
                title=article.title,
                url=article.url,
                source_name=article.source.name if article.source else None,
                published_at=published_at,
                content_hash=article.content_hash,
            )
        )
    return items


async def get_article_or_none(
    session: AsyncSession,
    article_id: int,
) -> RawArticle | None:
    result = await session.execute(
        select(RawArticle)
        .options(selectinload(RawArticle.source))
        .where(RawArticle.id == article_id)
    )
    return result.scalar_one_or_none()


def build_preview(article: RawArticle) -> str:
    return format_post(
        title=article.title,
        summary=article.summary,
        source_url=article.url,
    )
