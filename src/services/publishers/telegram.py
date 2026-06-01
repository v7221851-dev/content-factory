import httpx
from loguru import logger

from src.core.settings import settings
from src.services.publishers.base import PublishResult

TELEGRAM_CAPTION_MAX_CHARS = 1024
TELEGRAM_MESSAGE_MAX_CHARS = 4096
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class TelegramPublisher:
    platform = "telegram"

    def is_configured(self) -> bool:
        return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHANNEL_ID)

    def _chat_id(self) -> str:
        """Нормализует id канала: 100xxx… → -100xxx… (@username без изменений)."""
        raw = (settings.TELEGRAM_CHANNEL_ID or "").strip()
        if raw.startswith("@"):
            return raw
        if raw.isdigit() and raw.startswith("100"):
            return f"-{raw}"
        return raw

    def _api_url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"

    def _prepare_message(self, text: str, link: str | None) -> str:
        message = text
        if link and link not in text:
            message = f"{text}\n\n{link}"
        return message

    def _truncate(self, text: str, limit: int) -> tuple[str, bool]:
        if len(text) <= limit:
            return text, False
        return text[: limit - 1].rstrip() + "…", True

    async def _download_image(
        self,
        client: httpx.AsyncClient,
        image_url: str,
        referer: str | None,
    ) -> tuple[bytes, str] | tuple[None, str]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        if referer:
            headers["Referer"] = referer

        try:
            response = await client.get(
                image_url,
                headers=headers,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return None, f"скачивание: {exc}"

        content_type = response.headers.get("content-type", "").split(";")[0].strip()
        if content_type and not content_type.startswith("image/"):
            if content_type not in ("application/octet-stream", "binary/octet-stream"):
                return None, f"не изображение ({content_type})"

        if len(response.content) < 100:
            return None, "пустой или слишком маленький файл"

        mime = content_type if content_type.startswith("image/") else "image/jpeg"
        return response.content, mime

    def _result_from_response(self, data: dict) -> PublishResult:
        if not data.get("ok"):
            error = data.get("description", "Unknown Telegram error")
            if error == "Bad Request: chat not found":
                chat_id = self._chat_id()
                error = (
                    f"{error} (chat_id={chat_id}). "
                    "Публичный канал: TELEGRAM_CHANNEL_ID=@username из t.me/username. "
                    "Бот должен быть админом канала с правом публикации."
                )
            logger.error("Telegram API error: {}", error)
            return PublishResult(success=False, error=error)

        result = data.get("result", {})
        message_id = result.get("message_id")
        chat = result.get("chat", {})
        username = chat.get("username")
        external_id = str(message_id) if message_id is not None else None
        post_url = (
            f"https://t.me/{username}/{message_id}"
            if username and message_id is not None
            else None
        )

        logger.info("Telegram post published: message_id={}", message_id)
        return PublishResult(
            success=True,
            external_id=external_id,
            post_url=post_url,
        )

    async def _send_message(
        self,
        client: httpx.AsyncClient,
        message: str,
    ) -> PublishResult:
        text, truncated = self._truncate(message, TELEGRAM_MESSAGE_MAX_CHARS)
        url = self._api_url("sendMessage")
        payload = {
            "chat_id": self._chat_id(),
            "text": text,
            "disable_web_page_preview": False,
        }
        response = await client.post(url, json=payload)
        result = self._result_from_response(response.json())
        if result.success and truncated:
            result.warning = (
                f"Текст обрезан до {TELEGRAM_MESSAGE_MAX_CHARS} символов "
                "(лимит Telegram sendMessage)."
            )
        return result

    async def _send_photo(
        self,
        client: httpx.AsyncClient,
        caption: str,
        image_data: bytes,
        mime: str,
    ) -> PublishResult:
        caption_text, truncated = self._truncate(caption, TELEGRAM_CAPTION_MAX_CHARS)
        url = self._api_url("sendPhoto")
        ext = "jpg" if mime == "image/jpeg" else mime.split("/")[-1]
        response = await client.post(
            url,
            data={
                "chat_id": self._chat_id(),
                "caption": caption_text,
            },
            files={"photo": (f"image.{ext}", image_data, mime)},
        )
        result = self._result_from_response(response.json())
        if result.success and truncated:
            result.warning = (
                f"Подпись обрезана до {TELEGRAM_CAPTION_MAX_CHARS} символов "
                "(лимит Telegram sendPhoto)."
            )
        return result

    async def publish(
        self,
        text: str,
        link: str | None = None,
        image_url: str | None = None,
        image_referer: str | None = None,
    ) -> PublishResult:
        if not self.is_configured():
            return PublishResult(
                success=False,
                error=(
                    "Telegram не настроен: задайте TELEGRAM_BOT_TOKEN "
                    "и TELEGRAM_CHANNEL_ID в .env"
                ),
            )

        message = self._prepare_message(text, link)
        warning: str | None = None

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if image_url:
                    image_data, mime_or_error = await self._download_image(
                        client,
                        image_url,
                        referer=image_referer or link,
                    )
                    if image_data is not None:
                        result = await self._send_photo(
                            client,
                            caption=message,
                            image_data=image_data,
                            mime=mime_or_error,
                        )
                        if result.success:
                            return result
                        warning = f"Фото не опубликовано: {result.error}"
                        logger.warning("{} — {}", image_url, result.error)
                    else:
                        warning = f"Фото не прикреплено: {mime_or_error}"
                        logger.warning("{} — {}", image_url, mime_or_error)

                result = await self._send_message(client, message)
                if result.success and warning:
                    result.warning = warning
                return result
        except httpx.HTTPError as exc:
            logger.error("Telegram HTTP error: {}", exc)
            return PublishResult(success=False, error=str(exc))
