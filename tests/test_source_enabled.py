import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.core.db import Base
from src.models.entities import ArticleStatus, ContentSource, RawArticle
from src.services.ingest.rss import ingest_all_sources, ingest_source
from src.services.workflow.review import prepare_daily_review


async def _run() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        on = ContentSource(name="OnSource", feed_url="https://on.example/rss", enabled=True)
        off = ContentSource(name="OffSource", feed_url="https://off.example/rss", enabled=False)
        session.add_all([on, off])
        await session.commit()
        await session.refresh(on)
        await session.refresh(off)

        session.add_all(
            [
                RawArticle(
                    source_id=on.id,
                    title="On article",
                    url="https://on.example/a1",
                    content_hash="hash-on",
                    status=ArticleStatus.NEW,
                ),
                RawArticle(
                    source_id=off.id,
                    title="Off article",
                    url="https://off.example/a1",
                    content_hash="hash-off",
                    status=ArticleStatus.NEW,
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        disabled_result = await ingest_source(
            session,
            await session.scalar(
                select(ContentSource).where(ContentSource.name == "OffSource")
            ),
        )
        assert disabled_result.error == "source disabled"

        all_stats = await ingest_all_sources(session)
        assert "OffSource" not in all_stats
        assert "OnSource" not in all_stats  # fetch would fail; only enabled are queried

        enabled_names = {
            row.name
            for row in (
                await session.execute(
                    select(ContentSource).where(ContentSource.enabled.is_(True))
                )
            ).scalars()
        }
        assert enabled_names == {"OnSource"}

    async with session_factory() as session:
        result = await prepare_daily_review(session, limit=10)
        assert result.selected == 1

        off_article = await session.scalar(
            select(RawArticle).where(RawArticle.url == "https://off.example/a1")
        )
        on_article = await session.scalar(
            select(RawArticle).where(RawArticle.url == "https://on.example/a1")
        )
        assert off_article.status == ArticleStatus.NEW
        assert on_article.status == ArticleStatus.PENDING

    await engine.dispose()


def test_disabled_source_skips_ingest_and_review():
    asyncio.run(_run())
