from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthOut(BaseModel):
    status: str = "ok"
    configured_platforms: list[str]


class SourceIngestOut(BaseModel):
    fetched: int = 0
    new: int = 0
    skipped: int = 0
    error: Optional[str] = None


class IngestOut(BaseModel):
    sources: dict[str, SourceIngestOut]
    total_new: int


class ContentSourceOut(BaseModel):
    id: int
    name: str
    feed_url: str
    enabled: bool
    last_fetched_at: Optional[datetime] = None
    article_count: int = 0


class ContentSourceListOut(BaseModel):
    items: list[ContentSourceOut]


class ContentSourceCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    feed_url: str = Field(..., min_length=4, max_length=1024)
    enabled: bool = True


class ContentSourceUpdateIn(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    feed_url: Optional[str] = Field(None, min_length=4, max_length=1024)
    enabled: Optional[bool] = None


class ArticleOut(BaseModel):
    id: int
    title: str
    url: str
    summary: Optional[str]
    image_url: Optional[str] = None
    status: str
    fetched_at: datetime
    source_name: Optional[str] = None
    scheduled_publish_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ArticleListOut(BaseModel):
    items: list[ArticleOut]
    total: int


class ArticlePreviewOut(BaseModel):
    id: int
    title: str
    url: str
    summary: Optional[str]
    image_url: Optional[str] = None
    status: str
    source_name: Optional[str] = None
    formatted_text: str


class StatsOut(BaseModel):
    by_status: dict[str, int]
    pending_count: int
    daily_review_limit: int
    publish_interval_minutes: int
    configured_platforms: list[str]


class ArticleIdsIn(BaseModel):
    article_ids: list[int] = Field(..., min_length=1)


class PrepareReviewOut(BaseModel):
    selected: int
    already_pending: int
    available_new: int


class BatchRejectOut(BaseModel):
    rejected: int
    results: list[dict]


class PlatformPublishResult(BaseModel):
    platform: str
    success: bool
    external_id: Optional[str] = None
    post_url: Optional[str] = None
    error: Optional[str] = None
    warning: Optional[str] = None


class BatchPublishItemOut(BaseModel):
    article_id: int
    success: bool
    results: list[PlatformPublishResult] = Field(default_factory=list)
    error: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    published_now: bool = False


class BatchPublishOut(BaseModel):
    items: list[BatchPublishItemOut]
    published: int
    scheduled: int = 0
    failed: int


class PublishTextIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=16000)
    platforms: list[str] = Field(default=["vk"])
    link: Optional[str] = None
    image_url: Optional[str] = None


class PublishArticleIn(BaseModel):
    platforms: list[str] | None = None


class BatchPublishIn(BaseModel):
    article_ids: list[int] = Field(..., min_length=1)
    platforms: list[str] | None = None
    reject_remaining: bool = Field(
        default=False,
        description="Отклонить остальные pending после публикации выбранных",
    )


class PublishOut(BaseModel):
    results: list[PlatformPublishResult]


class PlatformsOut(BaseModel):
    available: list[str]
    configured: list[str]
