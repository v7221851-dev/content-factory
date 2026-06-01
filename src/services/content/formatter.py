import hashlib
import re
from html import unescape

from src.core.settings import get_settings


def _clean_html(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", text or "")
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _truncate(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _footer_block(source_url: str) -> str:
    cfg = get_settings()
    return "\n".join(
        [
            "",
            f"📰 Источник: {source_url}",
            "",
            "💜 MDSA — персональный помощник здоровья",
            f"👉 {cfg.MDSA_APP_URL}",
        ]
    )


def format_post(
    title: str,
    summary: str | None,
    source_url: str,
    *,
    max_total_chars: int | None = None,
) -> str:
    """Собирает пост. Учитывает заголовок и футер — влезает в TG (1024) и VK."""
    cfg = get_settings()
    title = title.strip()
    footer = _footer_block(source_url)
    body = _clean_html(summary) if summary else ""

    total_limit = max_total_chars if max_total_chars is not None else cfg.POST_MAX_TOTAL_CHARS
    # title + blank + body + blank + footer (если body есть — два \n\n)
    overhead = len(title) + len(footer) + (4 if body else 2)
    body_limit = min(cfg.POST_PREVIEW_MAX_CHARS, total_limit - overhead)
    body_limit = max(body_limit, 80)
    body = _truncate(body, body_limit) if body else ""

    parts = [title]
    if body:
        parts.extend(["", body])
    parts.append(footer)
    return "\n".join(parts)


def make_content_hash(title: str, url: str) -> str:
    payload = f"{title.strip()}|{url.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
