from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser
import httpx
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.entities import ArticleStatus, ContentSource, RawArticle
from src.services.content.formatter import make_content_hash
from src.services.content.images import extract_image_from_rss_entry


def _entry_summary(entry) -> str:
    """Берёт максимально полный текст из RSS (summary или content)."""
    candidates: list[str] = []
    for field in ("summary", "description", "subtitle"):
        value = entry.get(field)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip())

    content = entry.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                value = block.get("value") or ""
            else:
                value = str(block)
            if value.strip():
                candidates.append(value.strip())

    if not candidates:
        return ""
    return max(candidates, key=len)

# N+1 — общая наука, для MDSA обычно не подходит
DISABLED_SOURCE_NAMES: frozenset[str] = frozenset({"N+1"})

# Встроенные RSS (русский, здоровье / медицина). Новые имена добавляются при старте приложения.
# Medvestnik / Remedium убраны: их публичные /rss URL отдают 404.
DEFAULT_RSS_SOURCES: list[tuple[str, str]] = [
    ("Vademecum", "https://vademec.ru/rss/"),
    ("DoctorPiter", "https://doctorpiter.ru/rss/"),
    ("MedAboutMe", "https://medaboutme.ru/rss/"),
    ("Элементы", "https://elementy.ru/rss/news"),
    ("N+1", "https://nplus1.ru/rss"),
]

USER_AGENT = (
    "Mozilla/5.0 (compatible; MDSA-ContentFactory/1.0; +https://mdsa.tech)"
)


@dataclass
class IngestSourceResult:
    fetched: int = 0
    new: int = 0
    skipped: int = 0
    error: str | None = None


async def ensure_default_sources(session: AsyncSession) -> None:
    """Создаёт источники и обновляет URL. Делегирует в sources.py."""
    from src.services.ingest.sources import ensure_default_sources as _ensure

    await _ensure(session)


async def fetch_feed_entries(feed_url: str) -> list[dict]:
    async with httpx.AsyncClient(
        timeout=30.0,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        response = await client.get(feed_url)
        response.raise_for_status()
        content = response.content

    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        raise ValueError(parsed.bozo_exception or "Invalid RSS feed")

    entries: list[dict] = []
    for entry in parsed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        summary = _entry_summary(entry)
        image_url = extract_image_from_rss_entry(entry, base_url=link)
        entries.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "image_url": image_url,
                "content_hash": make_content_hash(title, link),
            }
        )
    return entries


async def ingest_source(session: AsyncSession, source: ContentSource) -> IngestSourceResult:
    if not source.enabled:
        return IngestSourceResult(error="source disabled")

    try:
        entries = await fetch_feed_entries(source.feed_url)
    except Exception as exc:
        logger.warning("RSS fetch failed for {} ({}): {}", source.name, source.feed_url, exc)
        return IngestSourceResult(error=str(exc))

    added = 0
    skipped = 0
    for entry in entries:
        existing_id = await session.scalar(
            select(RawArticle.id).where(RawArticle.url == entry["url"])
        )
        if existing_id is not None:
            article = await session.get(RawArticle, existing_id)
            if article:
                if entry.get("image_url") and not article.image_url:
                    article.image_url = entry["image_url"]
                new_summary = entry.get("summary") or ""
                old_summary = article.summary or ""
                if len(new_summary) > len(old_summary):
                    article.summary = new_summary
            skipped += 1
            continue

        session.add(
            RawArticle(
                source_id=source.id,
                title=entry["title"],
                url=entry["url"],
                summary=entry["summary"],
                image_url=entry.get("image_url"),
                content_hash=entry["content_hash"],
                status=ArticleStatus.NEW,
            )
        )
        added += 1

    source.last_fetched_at = datetime.now(timezone.utc)
    await session.commit()
    logger.info(
        "RSS {}: fetched={}, new={}, skipped={}",
        source.name,
        len(entries),
        added,
        skipped,
    )
    return IngestSourceResult(fetched=len(entries), new=added, skipped=skipped)


async def ingest_all_sources(session: AsyncSession) -> dict[str, IngestSourceResult]:
    await ensure_default_sources(session)
    result = await session.execute(
        select(ContentSource).where(ContentSource.enabled.is_(True))
    )
    sources = result.scalars().all()

    stats: dict[str, IngestSourceResult] = {}
    for source in sources:
        stats[source.name] = await ingest_source(session, source)
    return stats
