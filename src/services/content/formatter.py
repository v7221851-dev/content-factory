import hashlib
import re
from html import unescape

from src.core.settings import settings

DISCLAIMER = (
    "ℹ️ Информация носит ознакомительный характер "
    "и не заменяет консультацию врача."
)


def _clean_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def format_post(title: str, summary: str | None, source_url: str) -> str:
    body = _clean_html(summary) if summary else ""
    limit = settings.POST_PREVIEW_MAX_CHARS
    body = _truncate(body, limit) if body else ""

    parts = [title.strip()]
    if body:
        parts.append("")
        parts.append(body)
    parts.extend(
        [
            "",
            f"📰 Источник: {source_url}",
            "",
            f"💜 MDSA — персональный помощник здоровья",
            f"👉 {settings.MDSA_APP_URL}",
            "",
            DISCLAIMER,
        ]
    )
    return "\n".join(parts)


def make_content_hash(title: str, url: str) -> str:
    payload = f"{title.strip()}|{url.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
