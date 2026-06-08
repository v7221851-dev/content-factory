from datetime import datetime, timezone
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dto import (
    ArticleIdsIn,
    ArticleListOut,
    ArticleOut,
    ArticlePreviewOut,
    BatchPublishIn,
    BatchPublishItemOut,
    BatchPublishOut,
    BatchRejectOut,
    HealthOut,
    IngestOut,
    PlatformPublishResult,
    PlatformsOut,
    PrepareReviewOut,
    PublishedArticleOut,
    PublishArticleIn,
    PublishOut,
    PublishTextIn,
    RecentPublishedOut,
    SourceIngestOut,
    StatsOut,
)
from src.core.db import get_session
from src.core.deps import verify_api_key
from src.core.settings import settings
from src.models.entities import ArticleStatus, ContentSource, Platform, RawArticle
from src.services.content.formatter import format_post
from src.services.ingest.rss import ingest_all_sources
from src.services.publish.queue import schedule_or_publish_batch
from src.services.publish.service import publish_text_to_platforms
from src.services.publishers.registry import list_configured_platforms
from src.services.workflow.review import (
    build_preview,
    cancel_scheduled_articles,
    count_by_status,
    get_article_or_none,
    get_published_content_hashes,
    list_recently_published,
    prepare_daily_review,
    reject_all_pending,
    reject_articles,
)

ingest_router = APIRouter(prefix="/ingest", tags=["ingest"])
articles_router = APIRouter(prefix="/articles", tags=["articles"])
publish_router = APIRouter(prefix="/publish", tags=["publish"])
workflow_router = APIRouter(prefix="/workflow", tags=["workflow"])


def _resolve_platforms(platforms: list[str] | None) -> list[str]:
    return platforms or settings.publish_platforms_list


def _to_api_platform_results(results) -> list[PlatformPublishResult]:
    if not results:
        return []
    return [
        PlatformPublishResult(**asdict(r))
        if hasattr(r, "__dataclass_fields__")
        else r
        for r in results
    ]


def _to_api_publish_out(outcome) -> PublishOut:
    return PublishOut(results=_to_api_platform_results(outcome.results))


@ingest_router.post(
    "/rss",
    response_model=IngestOut,
    dependencies=[Depends(verify_api_key)],
    summary="Собрать новые статьи из RSS",
)
async def ingest_rss(session: AsyncSession = Depends(get_session)) -> IngestOut:
    stats = await ingest_all_sources(session)
    sources = {
        name: SourceIngestOut(
            fetched=result.fetched,
            new=result.new,
            skipped=result.skipped,
            error=result.error,
        )
        for name, result in stats.items()
    }
    return IngestOut(sources=sources, total_new=sum(r.new for r in stats.values()))


@articles_router.get(
    "",
    response_model=ArticleListOut,
    dependencies=[Depends(verify_api_key)],
    summary="Список статей",
)
async def list_articles(
    status_filter: str | None = Query(None, alias="status"),
    source: str | None = Query(None, description="Фильтр по источнику: DoctorPiter, Vademecum"),
    search: str | None = Query(None, description="Поиск по заголовку"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> ArticleListOut:
    order = (
        RawArticle.scheduled_publish_at.asc()
        if status_filter == ArticleStatus.SCHEDULED
        else RawArticle.fetched_at.desc()
    )
    query = (
        select(RawArticle)
        .options(selectinload(RawArticle.source))
        .order_by(order)
    )
    count_query = select(func.count()).select_from(RawArticle)

    if status_filter:
        query = query.where(RawArticle.status == status_filter)
        count_query = count_query.where(RawArticle.status == status_filter)

    if source:
        query = query.join(RawArticle.source).where(ContentSource.name == source)
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

    published_hashes = await get_published_content_hashes(session)

    items = [
        ArticleOut(
            id=a.id,
            title=a.title,
            url=a.url,
            summary=a.summary,
            image_url=a.image_url,
            status=a.status,
            fetched_at=a.fetched_at,
            source_name=a.source.name if a.source else None,
            scheduled_publish_at=a.scheduled_publish_at,
            is_duplicate=a.content_hash in published_hashes,
        )
        for a in articles
    ]
    return ArticleListOut(items=items, total=total)


@articles_router.get(
    "/stats",
    response_model=StatsOut,
    dependencies=[Depends(verify_api_key)],
    summary="Статистика по статьям",
)
async def article_stats(session: AsyncSession = Depends(get_session)) -> StatsOut:
    by_status = await count_by_status(session)
    return StatsOut(
        by_status=by_status,
        pending_count=by_status.get(ArticleStatus.PENDING, 0),
        daily_review_limit=settings.DAILY_REVIEW_LIMIT,
        publish_interval_minutes=settings.PUBLISH_INTERVAL_MINUTES,
        publish_queue_initial_delay_minutes=settings.PUBLISH_QUEUE_INITIAL_DELAY_MINUTES,
        configured_platforms=list_configured_platforms(),
    )


@articles_router.get(
    "/{article_id}/preview",
    response_model=ArticlePreviewOut,
    dependencies=[Depends(verify_api_key)],
    summary="Превью поста для согласования",
)
async def article_preview(
    article_id: int,
    session: AsyncSession = Depends(get_session),
) -> ArticlePreviewOut:
    article = await get_article_or_none(session, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    return ArticlePreviewOut(
        id=article.id,
        title=article.title,
        url=article.url,
        summary=article.summary,
        image_url=article.image_url,
        status=article.status,
        source_name=article.source.name if article.source else None,
        formatted_text=build_preview(article),
    )


@articles_router.post(
    "/reject",
    response_model=BatchRejectOut,
    dependencies=[Depends(verify_api_key)],
    summary="Отклонить выбранные статьи",
)
async def reject_selected_articles(
    body: ArticleIdsIn,
    session: AsyncSession = Depends(get_session),
) -> BatchRejectOut:
    results = await reject_articles(session, body.article_ids)
    rejected = sum(1 for r in results if r.success)
    return BatchRejectOut(
        rejected=rejected,
        results=[
            {"article_id": r.article_id, "success": r.success, "detail": r.detail}
            for r in results
        ],
    )


@articles_router.post(
    "/reject-pending",
    response_model=BatchRejectOut,
    dependencies=[Depends(verify_api_key)],
    summary="Отклонить все статьи в очереди согласования",
)
async def reject_pending_articles(
    session: AsyncSession = Depends(get_session),
) -> BatchRejectOut:
    count = await reject_all_pending(session)
    return BatchRejectOut(rejected=count, results=[])


@workflow_router.post(
    "/prepare-review",
    response_model=PrepareReviewOut,
    dependencies=[Depends(verify_api_key)],
    summary="Подготовить очередь на согласование (new → pending)",
)
async def prepare_review(
    limit: int | None = Query(None, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> PrepareReviewOut:
    result = await prepare_daily_review(session, limit=limit)
    return PrepareReviewOut(
        selected=result.selected,
        already_pending=result.already_pending,
        available_new=result.available_new,
    )


@workflow_router.post(
    "/cancel-scheduled",
    response_model=BatchRejectOut,
    dependencies=[Depends(verify_api_key)],
    summary="Убрать статьи из очереди публикации",
)
async def cancel_scheduled(
    body: ArticleIdsIn,
    session: AsyncSession = Depends(get_session),
) -> BatchRejectOut:
    results = await cancel_scheduled_articles(session, body.article_ids)
    cancelled = sum(1 for r in results if r.success)
    return BatchRejectOut(
        rejected=cancelled,
        results=[
            {"article_id": r.article_id, "success": r.success, "detail": r.detail}
            for r in results
        ],
    )


@workflow_router.get(
    "/recent-published",
    response_model=RecentPublishedOut,
    dependencies=[Depends(verify_api_key)],
    summary="Недавно опубликованные статьи",
)
async def recent_published(
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> RecentPublishedOut:
    items = await list_recently_published(session, days=days, limit=limit)
    return RecentPublishedOut(
        days=days,
        items=[
            PublishedArticleOut(
                id=item.id,
                title=item.title,
                url=item.url,
                source_name=item.source_name,
                published_at=item.published_at,
                content_hash=item.content_hash,
            )
            for item in items
        ],
    )


@publish_router.post(
    "/text",
    response_model=PublishOut,
    dependencies=[Depends(verify_api_key)],
    summary="Опубликовать произвольный текст",
)
async def publish_text(
    body: PublishTextIn,
    session: AsyncSession = Depends(get_session),
) -> PublishOut:
    outcome = await publish_text_to_platforms(
        session=session,
        text=body.text,
        platforms=_resolve_platforms(body.platforms),
        link=body.link,
        image_url=body.image_url,
    )
    return _to_api_publish_out(outcome)


@publish_router.post(
    "/articles/{article_id}",
    response_model=PublishOut,
    dependencies=[Depends(verify_api_key)],
    summary="Опубликовать статью из очереди",
)
async def publish_article(
    article_id: int,
    body: PublishArticleIn,
    session: AsyncSession = Depends(get_session),
) -> PublishOut:
    article = await get_article_or_none(session, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    if article.status not in (ArticleStatus.PENDING, ArticleStatus.NEW, ArticleStatus.READY):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Статья уже обработана (status={article.status})",
        )

    text = format_post(
        title=article.title,
        summary=article.summary,
        source_url=article.url,
    )
    outcome = await publish_text_to_platforms(
        session=session,
        text=text,
        platforms=_resolve_platforms(body.platforms),
        link=article.url,
        image_url=article.image_url,
        image_referer=article.url,
        article_id=article.id,
    )
    return _to_api_publish_out(outcome)


@publish_router.post(
    "/batch",
    response_model=BatchPublishOut,
    dependencies=[Depends(verify_api_key)],
    summary="Опубликовать несколько статей",
)
async def publish_batch(
    body: BatchPublishIn,
    session: AsyncSession = Depends(get_session),
) -> BatchPublishOut:
    platforms = _resolve_platforms(body.platforms)
    batch = await schedule_or_publish_batch(
        session,
        body.article_ids,
        platforms,
    )

    items = [
        BatchPublishItemOut(
            article_id=item.article_id,
            success=item.success,
            results=_to_api_platform_results(item.results),
            error=item.error,
            scheduled_at=item.scheduled_at,
            published_now=item.published_now,
        )
        for item in batch.items
    ]

    if body.reject_remaining:
        await reject_all_pending(session)

    return BatchPublishOut(
        items=items,
        published=batch.published,
        scheduled=batch.scheduled,
        failed=batch.failed,
    )


@publish_router.get(
    "/platforms",
    response_model=PlatformsOut,
    dependencies=[Depends(verify_api_key)],
    summary="Доступные платформы",
)
async def get_platforms() -> PlatformsOut:
    return PlatformsOut(
        available=[p.value for p in Platform],
        configured=list_configured_platforms(),
    )
