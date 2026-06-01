from dataclasses import dataclass


@dataclass
class PublishResult:
    success: bool
    external_id: str | None = None
    error: str | None = None
    post_url: str | None = None
    warning: str | None = None
