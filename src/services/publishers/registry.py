from src.models.entities import Platform
from src.services.publishers.base import PublishResult
from src.services.publishers.telegram import TelegramPublisher
from src.services.publishers.vk import VKPublisher

_PUBLISHERS = {
    Platform.VK.value: VKPublisher(),
    Platform.TELEGRAM.value: TelegramPublisher(),
}


def get_publisher(platform: str):
    publisher = _PUBLISHERS.get(platform.lower())
    if publisher is None:
        raise ValueError(f"Платформа «{platform}» пока не поддерживается")
    return publisher


def list_configured_platforms() -> list[str]:
    return [
        name
        for name, publisher in _PUBLISHERS.items()
        if publisher.is_configured()
    ]


async def publish_to_platform(
    platform: str,
    text: str,
    link: str | None = None,
    image_url: str | None = None,
    image_referer: str | None = None,
) -> PublishResult:
    publisher = get_publisher(platform)
    return await publisher.publish(
        text=text,
        link=link,
        image_url=image_url,
        image_referer=image_referer,
    )
