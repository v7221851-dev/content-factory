from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.db import Base


class ArticleStatus(StrEnum):
    NEW = "new"
    PENDING = "pending"
    SCHEDULED = "scheduled"
    READY = "ready"
    PUBLISHED = "published"
    SKIPPED = "skipped"


class PublishStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class Platform(StrEnum):
    VK = "vk"
    TELEGRAM = "telegram"
    LINKEDIN = "linkedin"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class ContentSource(Base):
    __tablename__ = "content_sources"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    feed_url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    articles: Mapped[list["RawArticle"]] = relationship(back_populates="source")


class RawArticle(Base):
    __tablename__ = "raw_articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("content_sources.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(2048))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ArticleStatus.NEW,
        server_default=ArticleStatus.NEW,
    )
    scheduled_publish_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    scheduled_platforms: Mapped[str | None] = mapped_column(String(128))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    source: Mapped[ContentSource | None] = relationship(back_populates="articles")
    posts: Mapped[list["PublishPost"]] = relationship(back_populates="article")


class PublishPost(Base):
    __tablename__ = "publish_posts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("raw_articles.id"))
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=PublishStatus.PENDING,
        server_default=PublishStatus.PENDING,
    )
    external_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    article: Mapped[RawArticle | None] = relationship(back_populates="posts")
