from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    CONTENT_FACTORY_API_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite+aiosqlite:///./content_factory.db"
    LOG_LEVEL: str = "INFO"

    VK_GROUP_ID: Optional[str] = None
    # Ключ сообщества — публикация на стену (wall.post)
    VK_ACCESS_TOKEN: Optional[str] = None
    # Ключ пользователя-админа — загрузка фото (photos.*). Обязателен для картинок.
    VK_USER_ACCESS_TOKEN: Optional[str] = None

    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHANNEL_ID: Optional[str] = None

    MDSA_APP_URL: str = "https://mdsa.tech"
    RSS_FETCH_INTERVAL_MINUTES: int = 0
    # Длина превью статьи в посте (~12–15 строк в VK)
    POST_PREVIEW_MAX_CHARS: int = 1800

    # Очередь согласования и автопубликация
    DAILY_REVIEW_LIMIT: int = 5
    DEFAULT_PUBLISH_PLATFORMS: str = "vk,telegram"
    DAILY_PREPARE_ENABLED: bool = True
    DAILY_PREPARE_HOUR: int = 8
    DAILY_PREPARE_MINUTE: int = 0

    # Интервал между публикациями статей (минуты). 0 = без задержки.
    PUBLISH_INTERVAL_MINUTES: int = 30

    @property
    def publish_platforms_list(self) -> list[str]:
        return [p.strip() for p in self.DEFAULT_PUBLISH_PLATFORMS.split(",") if p.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
