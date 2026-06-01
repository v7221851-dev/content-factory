from loguru import logger

from src.core.db import async_session
from src.core.settings import settings
from src.services.ingest.rss import ingest_all_sources
from src.services.publish.queue import publish_due_scheduled
from src.services.workflow.review import prepare_daily_review

_scheduler = None


async def _run_rss_ingest() -> None:
    logger.info("Scheduler: RSS ingest started")
    async with async_session() as session:
        stats = await ingest_all_sources(session)
        total_new = sum(r.new for r in stats.values())
        logger.info("Scheduler: RSS ingest done, new={}", total_new)


async def _run_prepare_review() -> None:
    logger.info("Scheduler: prepare daily review batch")
    async with async_session() as session:
        result = await prepare_daily_review(session)
        logger.info(
            "Scheduler: review batch selected={}, pending={}, new={}",
            result.selected,
            result.already_pending,
            result.available_new,
        )


async def _run_publish_due() -> None:
    async with async_session() as session:
        count = await publish_due_scheduled(session)
        if count:
            logger.info("Scheduler: опубликована запланированная статья")


def _run_async(coro_fn) -> None:
    import asyncio

    asyncio.run(coro_fn())


def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        lambda: _run_async(_run_publish_due),
        IntervalTrigger(seconds=60),
        id="publish_due",
        replace_existing=True,
    )

    if settings.RSS_FETCH_INTERVAL_MINUTES > 0:
        scheduler.add_job(
            lambda: _run_async(_run_rss_ingest),
            IntervalTrigger(minutes=settings.RSS_FETCH_INTERVAL_MINUTES),
            id="rss_ingest",
            replace_existing=True,
        )
        logger.info(
            "RSS ingest scheduled every {} min",
            settings.RSS_FETCH_INTERVAL_MINUTES,
        )

    if settings.DAILY_PREPARE_ENABLED:
        scheduler.add_job(
            lambda: _run_async(_run_prepare_review),
            CronTrigger(
                hour=settings.DAILY_PREPARE_HOUR,
                minute=settings.DAILY_PREPARE_MINUTE,
            ),
            id="daily_prepare_review",
            replace_existing=True,
        )
        logger.info(
            "Daily review batch at {:02d}:{:02d}",
            settings.DAILY_PREPARE_HOUR,
            settings.DAILY_PREPARE_MINUTE,
        )

    scheduler.start()
    _scheduler = scheduler
    logger.info(
        "Scheduler started ({} jobs, publish interval {} min)",
        len(scheduler.get_jobs()),
        settings.PUBLISH_INTERVAL_MINUTES,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
