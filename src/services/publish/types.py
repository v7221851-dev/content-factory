from dataclasses import dataclass, field


@dataclass
class PlatformPublishResult:
    platform: str
    success: bool
    external_id: str | None = None
    post_url: str | None = None
    error: str | None = None
    warning: str | None = None


@dataclass
class PublishOut:
    results: list[PlatformPublishResult] = field(default_factory=list)
