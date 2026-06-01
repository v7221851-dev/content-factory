from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import ArticleStatus, PublishPost, PublishStatus, RawArticle
from src.services.publish.types import PlatformPublishResult, PublishOut
from src.services.publishers.base import PublishResult
from src.services.publishers.registry import publish_to_platform


async def publish_text_to_platforms(
    session: AsyncSession,
    text: str,
    platforms: list[str],
    link: str | None,
    image_url: str | None = None,
    image_referer: str | None = None,
    article_id: int | None = None,
    *,
    mark_published: bool = True,
) -> PublishOut:
    results: list[PlatformPublishResult] = []

    for platform in platforms:
        try:
            outcome = await publish_to_platform(
                platform,
                text,
                link=link,
                image_url=image_url,
                image_referer=image_referer,
            )
        except ValueError as exc:
            outcome = PublishResult(success=False, error=str(exc))

        post_status = PublishStatus.PUBLISHED if outcome.success else PublishStatus.FAILED
        session.add(
            PublishPost(
                article_id=article_id,
                platform=platform,
                text=text,
                status=post_status,
                external_id=outcome.external_id,
                error_message=outcome.error or outcome.warning,
                published_at=datetime.now(timezone.utc) if outcome.success else None,
            )
        )

        results.append(
            PlatformPublishResult(
                platform=platform,
                success=outcome.success,
                external_id=outcome.external_id,
                post_url=outcome.post_url,
                error=outcome.error,
                warning=outcome.warning,
            )
        )

    if (
        mark_published
        and article_id is not None
        and any(r.success for r in results)
    ):
        article = await session.get(RawArticle, article_id)
        if article:
            article.status = ArticleStatus.PUBLISHED

    await session.commit()
    return PublishOut(results=results)
