from src.core.settings import settings
from src.services.content.formatter import format_post


def test_preview_uses_extended_limit(monkeypatch):
    monkeypatch.setattr(settings, "POST_PREVIEW_MAX_CHARS", 1800)
    long_body = "А" * 1500
    post = format_post("Заголовок", long_body, "https://example.com/a")
    assert "А" * 1500 in post
    assert "…" not in post.split("📰")[0]


def test_preview_truncates_beyond_limit(monkeypatch):
    monkeypatch.setattr(settings, "POST_PREVIEW_MAX_CHARS", 500)
    long_body = "Б" * 800
    post = format_post("Заголовок", long_body, "https://example.com/a")
    assert "…" in post
