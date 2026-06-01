from src.services.content.images import (
    extract_image_from_html,
    extract_image_from_rss_entry,
)


def test_extract_image_from_html():
    html = '<p>text</p><img src="https://cdn.example.com/a.jpg" alt="x">'
    assert extract_image_from_html(html) == "https://cdn.example.com/a.jpg"


def test_extract_image_from_html_relative():
    html = '<img src="/images/news.png">'
    assert (
        extract_image_from_html(html, "https://doctorpiter.ru/article/1")
        == "https://doctorpiter.ru/images/news.png"
    )


def test_extract_image_from_rss_entry_summary():
    entry = {
        "link": "https://doctorpiter.ru/article/1",
        "summary": '<img src="https://cdn.doctorpiter.ru/photo.jpg">',
    }
    assert (
        extract_image_from_rss_entry(entry)
        == "https://cdn.doctorpiter.ru/photo.jpg"
    )


def test_extract_image_from_rss_entry_media():
    entry = {
        "link": "https://example.com/a",
        "media_content": [{"url": "https://cdn.example.com/b.webp", "type": "image/webp"}],
    }
    assert extract_image_from_rss_entry(entry) == "https://cdn.example.com/b.webp"
