from fastapi import APIRouter

from src.api.dto import HealthOut
from src.api.v1.routes import articles_router, ingest_router, publish_router, workflow_router
from src.api.v1.sources_routes import sources_router
from src.services.publishers.registry import list_configured_platforms

router = APIRouter()
v1_router = APIRouter(prefix="/v1")

v1_router.include_router(ingest_router)
v1_router.include_router(sources_router)
v1_router.include_router(articles_router)
v1_router.include_router(publish_router)
v1_router.include_router(workflow_router)
router.include_router(v1_router)


@router.get("/health", response_model=HealthOut, tags=["system"])
async def health() -> HealthOut:
    return HealthOut(configured_platforms=list_configured_platforms())
