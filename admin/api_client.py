"""HTTP-клиент к Content Factory API для Streamlit."""

from __future__ import annotations

from typing import Any

import httpx


class ContentFactoryClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        with httpx.Client(timeout=120.0) as client:
            response = client.request(
                method,
                self._url(path),
                headers=self.headers,
                **kwargs,
            )
            response.raise_for_status()
            if response.content:
                return response.json()
            return None

    def stats(self) -> dict:
        return self._request("GET", "/v1/articles/stats")

    def list_articles(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if source:
            params["source"] = source
        if search:
            params["search"] = search
        return self._request("GET", "/v1/articles", params=params)

    def preview(self, article_id: int) -> dict:
        return self._request("GET", f"/v1/articles/{article_id}/preview")

    def ingest_rss(self) -> dict:
        return self._request("POST", "/v1/ingest/rss")

    def list_sources(self) -> dict:
        return self._request("GET", "/v1/sources")

    def create_source(
        self,
        name: str,
        feed_url: str,
        *,
        enabled: bool = True,
        validate: bool = True,
    ) -> dict:
        return self._request(
            "POST",
            "/v1/sources",
            params={"validate": validate},
            json={"name": name, "feed_url": feed_url, "enabled": enabled},
        )

    def update_source(
        self,
        source_id: int,
        *,
        name: str | None = None,
        feed_url: str | None = None,
        enabled: bool | None = None,
        validate: bool = True,
    ) -> dict:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if feed_url is not None:
            body["feed_url"] = feed_url
        if enabled is not None:
            body["enabled"] = enabled
        return self._request(
            "PATCH",
            f"/v1/sources/{source_id}",
            params={"validate": validate},
            json=body,
        )

    def delete_source(self, source_id: int) -> dict:
        return self._request("DELETE", f"/v1/sources/{source_id}")

    def ingest_source(self, source_id: int) -> dict:
        return self._request("POST", f"/v1/sources/{source_id}/ingest")

    def prepare_review(self, limit: int | None = None) -> dict:
        params = {"limit": limit} if limit else None
        return self._request("POST", "/v1/workflow/prepare-review", params=params)

    def publish_batch(
        self,
        article_ids: list[int],
        *,
        platforms: list[str] | None = None,
        reject_remaining: bool = False,
    ) -> dict:
        body: dict[str, Any] = {
            "article_ids": article_ids,
            "reject_remaining": reject_remaining,
        }
        if platforms:
            body["platforms"] = platforms
        return self._request("POST", "/v1/publish/batch", json=body)

    def reject_articles(self, article_ids: list[int]) -> dict:
        return self._request(
            "POST",
            "/v1/articles/reject",
            json={"article_ids": article_ids},
        )

    def reject_all_pending(self) -> dict:
        return self._request("POST", "/v1/articles/reject-pending")

    def platforms(self) -> dict:
        return self._request("GET", "/v1/publish/platforms")

    def health(self) -> dict:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(self._url("/health"))
            response.raise_for_status()
            return response.json()
