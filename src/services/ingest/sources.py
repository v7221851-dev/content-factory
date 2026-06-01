from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import ContentSource, RawArticle
from src.services.ingest.rss import (
    DEFAULT_RSS_SOURCES,
    DISABLED_SOURCE_NAMES,
    IngestSourceResult,
    fetch_feed_entries,
    ingest_source,
)


@dataclass
class SourceOut:
    id: int
    name: str
    feed_url: str
    enabled: bool
    last_fetched_at: datetime | None
    article_count: int


async def list_sources(session: AsyncSession) -> list[SourceOut]:
    result = await session.execute(
        select(ContentSource).order_by(ContentSource.name.asc())
    )
    sources = result.scalars().all()
    items: list[SourceOut] = []
    for source in sources:
        count = await session.scalar(
            select(func.count())
            .select_from(RawArticle)
            .where(RawArticle.source_id == source.id)
        ) or 0
        items.append(
            SourceOut(
                id=source.id,
                name=source.name,
                feed_url=source.feed_url,
                enabled=source.enabled,
                last_fetched_at=source.last_fetched_at,
                article_count=count,
            )
        )
    return items


async def get_source(session: AsyncSession, source_id: int) -> ContentSource | None:
    return await session.get(ContentSource, source_id)


async def create_source(
    session: AsyncSession,
    name: str,
    feed_url: str,
    *,
    enabled: bool = True,
    validate: bool = True,
) -> ContentSource:
    name = name.strip()
    feed_url = feed_url.strip()
    if not name or not feed_url:
        raise ValueError("name и feed_url обязательны")

    existing = await session.scalar(
        select(ContentSource.id).where(ContentSource.name == name)
    )
    if existing is not None:
        raise ValueError(f"Источник «{name}» уже существует")

    duplicate_url = await session.scalar(
        select(ContentSource.id).where(ContentSource.feed_url == feed_url)
    )
    if duplicate_url is not None:
        raise ValueError("Этот RSS URL уже добавлен")

    if validate:
        await _validate_feed_url(feed_url)

    source = ContentSource(name=name, feed_url=feed_url, enabled=enabled)
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return source


async def update_source(
    session: AsyncSession,
    source_id: int,
    *,
    name: str | None = None,
    feed_url: str | None = None,
    enabled: bool | None = None,
    validate: bool = True,
) -> ContentSource:
    source = await get_source(session, source_id)
    if source is None:
        raise ValueError("Источник не найден")

    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("name не может быть пустым")
        other = await session.scalar(
            select(ContentSource.id).where(
                ContentSource.name == name,
                ContentSource.id != source_id,
            )
        )
        if other is not None:
            raise ValueError(f"Источник «{name}» уже существует")
        source.name = name

    if feed_url is not None:
        feed_url = feed_url.strip()
        if not feed_url:
            raise ValueError("feed_url не может быть пустым")
        other = await session.scalar(
            select(ContentSource.id).where(
                ContentSource.feed_url == feed_url,
                ContentSource.id != source_id,
            )
        )
        if other is not None:
            raise ValueError("Этот RSS URL уже добавлен")
        if validate:
            await _validate_feed_url(feed_url)
        source.feed_url = feed_url

    if enabled is not None:
        source.enabled = enabled

    await session.commit()
    await session.refresh(source)
    return source


async def delete_source(session: AsyncSession, source_id: int) -> None:
    source = await get_source(session, source_id)
    if source is None:
        raise ValueError("Источник не найден")

    article_count = await session.scalar(
        select(func.count())
        .select_from(RawArticle)
        .where(RawArticle.source_id == source_id)
    ) or 0
    if article_count > 0:
        raise ValueError(
            f"Нельзя удалить: {article_count} статей привязано к источнику. "
            "Отключите источник вместо удаления."
        )

    await session.delete(source)
    await session.commit()


async def ingest_one_source(
    session: AsyncSession,
    source_id: int,
) -> IngestSourceResult:
    source = await get_source(session, source_id)
    if source is None:
        raise ValueError("Источник не найден")
    return await ingest_source(session, source)


async def _validate_feed_url(feed_url: str) -> None:
    entries = await fetch_feed_entries(feed_url)
    if not entries:
        raise ValueError("RSS-лента пуста или недоступна")


async def ensure_default_sources(session: AsyncSession) -> None:
    """Создаёт встроенные источники, если их ещё нет. Не перезаписывает enabled."""
    result = await session.execute(select(ContentSource))
    existing = {source.name: source for source in result.scalars().all()}

    for name, feed_url in DEFAULT_RSS_SOURCES:
        source = existing.get(name)
        if source is None:
            session.add(
                ContentSource(
                    name=name,
                    feed_url=feed_url,
                    enabled=name not in DISABLED_SOURCE_NAMES,
                )
            )
            continue
        if source.feed_url != feed_url:
            source.feed_url = feed_url

    await session.commit()
