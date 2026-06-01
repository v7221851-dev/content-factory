from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dto import (
    ContentSourceCreateIn,
    ContentSourceListOut,
    ContentSourceOut,
    ContentSourceUpdateIn,
    SourceIngestOut,
)
from src.core.db import get_session
from src.core.deps import verify_api_key
from src.services.ingest.sources import (
    create_source,
    delete_source,
    ingest_one_source,
    list_sources,
    update_source,
)

sources_router = APIRouter(prefix="/sources", tags=["sources"])


def _to_out(item) -> ContentSourceOut:
    return ContentSourceOut(
        id=item.id,
        name=item.name,
        feed_url=item.feed_url,
        enabled=item.enabled,
        last_fetched_at=item.last_fetched_at,
        article_count=item.article_count,
    )


@sources_router.get(
    "",
    response_model=ContentSourceListOut,
    dependencies=[Depends(verify_api_key)],
    summary="Список RSS-источников",
)
async def get_sources(session: AsyncSession = Depends(get_session)) -> ContentSourceListOut:
    items = await list_sources(session)
    return ContentSourceListOut(items=[_to_out(i) for i in items])


@sources_router.post(
    "",
    response_model=ContentSourceOut,
    dependencies=[Depends(verify_api_key)],
    summary="Добавить RSS-источник",
)
async def add_source(
    body: ContentSourceCreateIn,
    validate: bool = Query(True, description="Проверить RSS перед сохранением"),
    session: AsyncSession = Depends(get_session),
) -> ContentSourceOut:
    try:
        source = await create_source(
            session,
            body.name,
            body.feed_url,
            enabled=body.enabled,
            validate=validate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    items = await list_sources(session)
    found = next((i for i in items if i.id == source.id), None)
    if found is None:
        raise HTTPException(status_code=500, detail="Source created but not found")
    return _to_out(found)


@sources_router.patch(
    "/{source_id}",
    response_model=ContentSourceOut,
    dependencies=[Depends(verify_api_key)],
    summary="Обновить RSS-источник",
)
async def patch_source(
    source_id: int,
    body: ContentSourceUpdateIn,
    validate: bool = Query(True),
    session: AsyncSession = Depends(get_session),
) -> ContentSourceOut:
    try:
        source = await update_source(
            session,
            source_id,
            name=body.name,
            feed_url=body.feed_url,
            enabled=body.enabled,
            validate=validate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    items = await list_sources(session)
    found = next((i for i in items if i.id == source.id), None)
    if found is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return _to_out(found)


@sources_router.delete(
    "/{source_id}",
    dependencies=[Depends(verify_api_key)],
    summary="Удалить RSS-источник",
)
async def remove_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        await delete_source(session, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"ok": True}


@sources_router.post(
    "/{source_id}/ingest",
    response_model=SourceIngestOut,
    dependencies=[Depends(verify_api_key)],
    summary="Собрать RSS одного источника",
)
async def ingest_single_source(
    source_id: int,
    session: AsyncSession = Depends(get_session),
) -> SourceIngestOut:
    try:
        result = await ingest_one_source(session, source_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return SourceIngestOut(
        fetched=result.fetched,
        new=result.new,
        skipped=result.skipped,
        error=result.error,
    )
