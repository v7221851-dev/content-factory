import re
from html import unescape
from urllib.parse import urljoin, urlparse

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}


def _looks_like_image(content_type: str | None, url: str) -> bool:
    if content_type and content_type.startswith("image/"):
        return True
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def _normalize_url(url: str, base_url: str | None) -> str:
    cleaned = unescape(url.strip())
    if base_url and not urlparse(cleaned).netloc:
        return urljoin(base_url, cleaned)
    return cleaned


def extract_image_from_html(html: str, base_url: str | None = None) -> str | None:
    if not html:
        return None

    for match in re.finditer(
        r"""<img[^>]+src=["']([^"']+)["']""",
        html,
        flags=re.IGNORECASE,
    ):
        url = _normalize_url(match.group(1), base_url)
        if url and not url.startswith("data:"):
            return url
    return None


def extract_image_from_rss_entry(entry: dict, base_url: str | None = None) -> str | None:
    """Извлекает URL обложки из RSS-записи feedparser."""
    link = base_url or entry.get("link") or entry.get("url")

    for key in ("media_content", "media_thumbnail"):
        for item in entry.get(key) or []:
            url = item.get("url")
            if url and _looks_like_image(item.get("type"), url):
                return _normalize_url(url, link)

    for enclosure in entry.get("enclosures") or []:
        url = enclosure.get("href") or enclosure.get("url")
        if url and _looks_like_image(enclosure.get("type"), url):
            return _normalize_url(url, link)

    for item in entry.get("links") or []:
        if item.get("rel") == "enclosure":
            url = item.get("href")
            if url and _looks_like_image(item.get("type"), url):
                return _normalize_url(url, link)

    for field in ("summary", "description", "content"):
        value = entry.get(field)
        if isinstance(value, list):
            for block in value:
                html = block.get("value") if isinstance(block, dict) else str(block)
                image = extract_image_from_html(html or "", link)
                if image:
                    return image
        elif isinstance(value, str):
            image = extract_image_from_html(value, link)
            if image:
                return image

    return None
