import httpx
from loguru import logger

from src.core.settings import settings
from src.services.publishers.base import PublishResult

VK_API_VERSION = "5.199"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class VKPublisher:
    platform = "vk"

    def is_configured(self) -> bool:
        return bool(settings.VK_GROUP_ID and settings.VK_ACCESS_TOKEN)

    def _wall_access_token(self) -> str:
        return settings.VK_ACCESS_TOKEN  # type: ignore[return-value]

    def _photo_access_token(self) -> str | None:
        # photos.getWallUploadServer не работает с ключом сообщества
        return settings.VK_USER_ACCESS_TOKEN

    async def _vk_api_get(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: dict[str, str | int],
    ) -> dict:
        response = await client.get(
            f"https://api.vk.com/method/{method}",
            params=params,
        )
        return response.json()

    async def _vk_api_post(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: dict[str, str | int],
    ) -> dict:
        response = await client.post(
            f"https://api.vk.com/method/{method}",
            data=params,
        )
        return response.json()

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
            image_response = await client.get(
                image_url,
                headers=headers,
                follow_redirects=True,
            )
            image_response.raise_for_status()
        except httpx.HTTPError as exc:
            return None, f"скачивание: {exc}"

        content_type = image_response.headers.get("content-type", "").split(";")[0].strip()
        if content_type and not content_type.startswith("image/"):
            if content_type not in ("application/octet-stream", "binary/octet-stream"):
                return None, f"не изображение ({content_type})"

        if len(image_response.content) < 100:
            return None, "пустой или слишком маленький файл"

        mime = content_type if content_type.startswith("image/") else "image/jpeg"
        return image_response.content, mime

    async def _upload_wall_photo(
        self,
        client: httpx.AsyncClient,
        image_url: str,
        group_id: str,
        referer: str | None = None,
    ) -> tuple[str | None, str | None]:
        image_data, mime_or_error = await self._download_image(
            client,
            image_url,
            referer,
        )
        if image_data is None:
            logger.warning("Не удалось скачать {}: {}", image_url, mime_or_error)
            return None, mime_or_error

        photo_token = self._photo_access_token()
        if not photo_token:
            return None, (
                "нужен VK_USER_ACCESS_TOKEN (ключ пользователя-админа с photos, wall, groups). "
                "Ключ сообщества не умеет загружать фото."
            )

        mime = mime_or_error
        upload_payload = await self._vk_api_get(
            client,
            "photos.getWallUploadServer",
            {
                "group_id": group_id.lstrip("-"),
                "access_token": photo_token,
                "v": VK_API_VERSION,
            },
        )
        if "error" in upload_payload:
            error = upload_payload["error"].get("error_msg", str(upload_payload["error"]))
            logger.error("VK getWallUploadServer: {}", error)
            return None, error

        upload_url = upload_payload["response"]["upload_url"]
        try:
            upload_response = await client.post(
                upload_url,
                files={"photo": ("image.jpg", image_data, mime)},
            )
            upload_response.raise_for_status()
            upload_data = upload_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("VK photo upload: {}", exc)
            return None, str(exc)

        if not all(key in upload_data for key in ("server", "photo", "hash")):
            return None, f"некорректный ответ upload-сервера: {upload_data}"

        save_payload = await self._vk_api_post(
            client,
            "photos.saveWallPhoto",
            {
                "group_id": group_id.lstrip("-"),
                "server": str(upload_data["server"]),
                "photo": upload_data["photo"],
                "hash": upload_data["hash"],
                "access_token": photo_token,
                "v": VK_API_VERSION,
            },
        )
        if "error" in save_payload:
            error = save_payload["error"].get("error_msg", str(save_payload["error"]))
            logger.error("VK saveWallPhoto: {}", error)
            return None, error

        photo = save_payload["response"][0]
        return f"photo{photo['owner_id']}_{photo['id']}", None

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
                error="VK не настроен: задайте VK_GROUP_ID и VK_ACCESS_TOKEN в .env",
            )

        group_id = settings.VK_GROUP_ID.strip()
        owner_id = f"-{group_id.lstrip('-')}"
        warning: str | None = None

        params: dict[str, str | int] = {
            "owner_id": owner_id,
            "from_group": 1,
            "message": text,
            "access_token": self._wall_access_token(),
            "v": VK_API_VERSION,
        }

        attachments: list[str] = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                if image_url:
                    photo_attachment, photo_error = await self._upload_wall_photo(
                        client,
                        image_url=image_url,
                        group_id=group_id,
                        referer=image_referer or link,
                    )
                    if photo_attachment:
                        attachments.append(photo_attachment)
                    else:
                        warning = (
                            f"Фото не прикреплено: {photo_error}. "
                            "Проверьте права токена VK (photos, wall)."
                        )
                        logger.warning("{} — {}", image_url, photo_error)

                if link and attachments:
                    attachments.append(link)

                if attachments:
                    params["attachments"] = ",".join(attachments)

                response = await client.post(
                    "https://api.vk.com/method/wall.post",
                    data=params,
                )
                payload = response.json()
        except httpx.HTTPError as exc:
            logger.error("VK HTTP error: {}", exc)
            return PublishResult(success=False, error=str(exc))

        if "error" in payload:
            error = payload["error"]
            message = error.get("error_msg", str(error))
            logger.error("VK API error: {}", message)
            return PublishResult(success=False, error=message)

        post_id = payload.get("response", {}).get("post_id")
        external_id = str(post_id) if post_id is not None else None
        post_url = (
            f"https://vk.com/wall{owner_id}_{post_id}"
            if post_id is not None
            else None
        )

        logger.info("VK post published: {}", post_url)
        return PublishResult(
            success=True,
            external_id=external_id,
            post_url=post_url,
            warning=warning,
        )
