from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.settings import settings
from src.models.entities import ArticleStatus, RawArticle
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
        new_count = await session.scalar(
            select(func.count())
            .select_from(RawArticle)
            .where(RawArticle.status == ArticleStatus.NEW)
        ) or 0
        return PrepareReviewResult(
            selected=0,
            already_pending=pending_count,
            available_new=new_count,
        )

    slots = batch_size - pending_count
    result = await session.execute(
        select(RawArticle)
        .where(RawArticle.status == ArticleStatus.NEW)
        .order_by(RawArticle.fetched_at.desc())
        .limit(slots)
    )
    articles = result.scalars().all()

    for article in articles:
        article.status = ArticleStatus.PENDING

    await session.commit()

    new_count = await session.scalar(
        select(func.count())
        .select_from(RawArticle)
        .where(RawArticle.status == ArticleStatus.NEW)
    ) or 0

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


async def reject_all_pending(session: AsyncSession) -> int:
    result = await session.execute(
        select(RawArticle).where(RawArticle.status == ArticleStatus.PENDING)
    )
    articles = result.scalars().all()
    for article in articles:
        article.status = ArticleStatus.SKIPPED
    await session.commit()
    return len(articles)


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
