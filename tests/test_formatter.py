from src.core.settings import get_settings
from src.services.content.formatter import format_post


def test_preview_respects_total_limit(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "POST_PREVIEW_MAX_CHARS", 900)
    monkeypatch.setattr(cfg, "POST_MAX_TOTAL_CHARS", 1024)
    long_body = "А" * 2000
    post = format_post("Заголовок", long_body, "https://example.com/a")
    assert len(post) <= 1024
    assert "📰 Источник:" in post


def test_preview_truncates_beyond_body_limit(monkeypatch):
    cfg = get_settings()
    monkeypatch.setattr(cfg, "POST_PREVIEW_MAX_CHARS", 200)
    monkeypatch.setattr(cfg, "POST_MAX_TOTAL_CHARS", 4096)
    long_body = "Б" * 800
    post = format_post("Заголовок", long_body, "https://example.com/a")
    assert "…" in post
