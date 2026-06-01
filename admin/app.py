"""MDSA Content Factory — панель управления."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from admin.api_client import ContentFactoryClient
from admin.embedded import EmbeddedBackend

st.set_page_config(
    page_title="MDSA Content Factory",
    page_icon="📰",
    layout="wide",
)

DEFAULT_API = os.getenv("CONTENT_FACTORY_URL", "http://127.0.0.1:8090")
DEFAULT_KEY = os.getenv("CONTENT_FACTORY_API_KEY", "change-me")


def _apply_secrets_to_env() -> None:
    """Streamlit Cloud: secrets.toml. Локально достаточно content-factory/.env."""
    secrets_paths = [
        ROOT / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    if not any(p.is_file() for p in secrets_paths):
        return
    try:
        for key, value in st.secrets.items():
            if isinstance(value, (str, int, float, bool)):
                os.environ[str(key)] = str(value)
    except Exception:
        pass
    try:
        from src.core.settings import get_settings

        get_settings.cache_clear()
    except Exception:
        pass


def _embedded_mode() -> bool:
    mode = os.getenv("CONTENT_FACTORY_MODE", "").strip().lower()
    return mode in ("embedded", "direct", "")


def get_client() -> ContentFactoryClient | EmbeddedBackend:
    if _embedded_mode():
        if "embedded_client" not in st.session_state:
            st.session_state.embedded_client = EmbeddedBackend()
        return st.session_state.embedded_client
    return ContentFactoryClient(st.session_state.api_url, st.session_state.api_key)


def init_state() -> None:
    _apply_secrets_to_env()
    st.session_state.setdefault("api_url", DEFAULT_API)
    st.session_state.setdefault("api_key", DEFAULT_KEY)
    st.session_state.setdefault("selected_ids", set())
    if _embedded_mode():
        get_client()  # запуск scheduler через _ensure_ready


def sidebar() -> str:
    st.sidebar.title("Content Factory")

    if _embedded_mode():
        st.sidebar.caption("Режим: embedded (без отдельного API)")
    else:
        st.session_state.api_url = st.sidebar.text_input(
            "API URL",
            value=st.session_state.api_url,
        )
        st.session_state.api_key = st.sidebar.text_input(
            "API Key",
            value=st.session_state.api_key,
            type="password",
        )

    try:
        health = get_client().health()
        st.sidebar.success(
            f"OK · платформы: {', '.join(health.get('configured_platforms', [])) or '—'}"
        )
    except Exception as exc:
        st.sidebar.error(f"Ошибка: {exc}")

    return st.sidebar.radio(
        "Раздел",
        ["Главная", "Сбор новостей", "Согласование", "Каталог"],
        label_visibility="collapsed",
    )


def page_home() -> None:
    st.header("Главная")
    try:
        stats = get_client().stats()
    except Exception as exc:
        st.error(f"Не удалось загрузить статистику: {exc}")
        return

    cols = st.columns(5)
    by_status = stats.get("by_status", {})
    cols[0].metric("Новые", by_status.get("new", 0))
    cols[1].metric("На согласовании", stats.get("pending_count", 0))
    cols[2].metric("Запланированы", by_status.get("scheduled", 0))
    cols[3].metric("Опубликовано", by_status.get("published", 0))
    cols[4].metric("Отклонено", by_status.get("skipped", 0))

    st.info(
        f"Ежедневная очередь: **{stats.get('daily_review_limit', 5)}** статей. "
        f"Платформы: **{', '.join(stats.get('configured_platforms', []))}**. "
        f"Интервал между публикациями: **{stats.get('publish_interval_minutes', 30)} мин**."
    )
    st.caption(
        "**На согласовании** — статьи ждут вашего решения (раздел «Согласование»). "
        "**Запланированы** — одобрены и выйдут в VK/TG автоматически по расписанию."
    )

    st.markdown(
        """
**Рабочий процесс**
1. **Сбор новостей** — собрать RSS и накопить статьи.
2. **Согласование** — подготовить очередь (5 шт.), прочитать, опубликовать или отклонить.
3. Автоматически: RSS по расписанию и подготовка очереди утром (если включено в `.env`).
        """
    )


def page_ingest() -> None:
    st.header("Сбор новостей")
    client = get_client()

    st.subheader("RSS-источники")
    try:
        sources_data = client.list_sources()
        sources = sources_data.get("items", [])
    except Exception as exc:
        st.error(f"Не удалось загрузить источники: {exc}")
        sources = []

    if sources:
        for src in sources:
            col1, col2, col3, col4 = st.columns([3, 4, 1, 2])
            with col1:
                enabled = st.toggle(
                    "Вкл.",
                    value=src["enabled"],
                    key=f"src_en_{src['id']}",
                )
                if enabled != src["enabled"]:
                    try:
                        client.update_source(src["id"], enabled=enabled, validate=False)
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                st.markdown(f"**{src['name']}**")
                st.caption(f"Статей: {src.get('article_count', 0)}")
            with col2:
                new_url = st.text_input(
                    "RSS URL",
                    value=src["feed_url"],
                    key=f"src_url_{src['id']}",
                    label_visibility="collapsed",
                )
            with col3:
                if st.button("💾", key=f"src_save_{src['id']}", help="Сохранить URL"):
                    try:
                        client.update_source(
                            src["id"],
                            feed_url=new_url,
                            validate=True,
                        )
                        st.success("Сохранено")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            with col4:
                if st.button("Собрать", key=f"src_ing_{src['id']}"):
                    with st.spinner("..."):
                        try:
                            r = client.ingest_source(src["id"])
                            st.success(f"+{r.get('new', 0)} новых")
                            if r.get("error"):
                                st.warning(r["error"])
                        except Exception as exc:
                            st.error(str(exc))
                if st.button("🗑", key=f"src_del_{src['id']}", help="Удалить"):
                    try:
                        client.delete_source(src["id"])
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            last = src.get("last_fetched_at")
            if last:
                st.caption(f"Последний сбор: {last[:16]}")
            st.divider()
    else:
        st.caption("Нет источников — добавьте ниже.")

    with st.expander("➕ Добавить источник", expanded=not sources):
        new_name = st.text_input("Название", placeholder="MedNews")
        new_url = st.text_input("RSS URL", placeholder="https://example.com/rss")
        new_enabled = st.checkbox("Включён", value=True)
        skip_validate = st.checkbox("Без проверки RSS (быстро)", value=False)
        if st.button("Добавить источник"):
            if not new_name or not new_url:
                st.error("Укажите название и URL")
            else:
                try:
                    client.create_source(
                        new_name,
                        new_url,
                        enabled=new_enabled,
                        validate=not skip_validate,
                    )
                    st.success(f"Источник «{new_name}» добавлен")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    if st.button("Собрать RSS со всех включённых", type="primary"):
        with st.spinner("Сбор..."):
            try:
                result = client.ingest_rss()
                st.success(f"Добавлено новых статей: {result.get('total_new', 0)}")
                for name, src in result.get("sources", {}).items():
                    st.write(
                        f"**{name}**: получено {src.get('fetched', 0)}, "
                        f"новых {src.get('new', 0)}, пропущено {src.get('skipped', 0)}"
                    )
                    if src.get("error"):
                        st.warning(src["error"])
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.subheader("Новые статьи в базе")
    try:
        data = client.list_articles(status="new", limit=20)
        if not data["items"]:
            st.caption("Нет новых статей — нажмите «Собрать RSS».")
        for item in data["items"]:
            with st.expander(f"#{item['id']} · {item['title'][:100]}"):
                st.caption(f"{item.get('source_name')} · {item['url']}")
                if item.get("summary"):
                    st.write(item["summary"][:500])
                if item.get("image_url"):
                    st.image(item["image_url"], width=300)
    except Exception as exc:
        st.error(str(exc))


def page_review() -> None:
    st.header("Согласование")
    client = get_client()

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Подготовить очередь на сегодня"):
            try:
                result = client.prepare_review()
                st.success(
                    f"В очередь добавлено: {result['selected']}. "
                    f"Уже на согласовании: {result['already_pending']}. "
                    f"Новых в базе: {result['available_new']}."
                )
            except Exception as exc:
                st.error(str(exc))

    try:
        pending = client.list_articles(status="pending", limit=50)
    except Exception as exc:
        st.error(str(exc))
        return

    items = pending["items"]
    if not items:
        st.info("Очередь пуста. Нажмите «Подготовить очередь» или соберите RSS.")
        return

    st.write(f"Статей на согласовании: **{len(items)}**")
    st.caption(
        "Здесь статьи ждут вашего решения. После «Опубликовать» первая уйдёт сразу, "
        "остальные попадут в «Запланированы» на главной (интервал 30 мин)."
    )

    selected: set[int] = set()
    for item in items:
        checked = st.checkbox(
            f"#{item['id']} · {item['title']}",
            value=True,
            key=f"sel_{item['id']}",
        )
        if checked:
            selected.add(item["id"])

        with st.expander("Превью поста", expanded=False):
            try:
                preview = client.preview(item["id"])
                if preview.get("image_url"):
                    st.image(preview["image_url"], width=400)
                st.text_area(
                    "Текст для VK / Telegram",
                    preview["formatted_text"],
                    height=280,
                    disabled=True,
                    key=f"preview_{item['id']}",
                )
                st.link_button("Открыть источник", preview["url"])
            except Exception as exc:
                st.warning(str(exc))
        st.divider()

    st.divider()
    st.subheader("Запланированные публикации")
    try:
        scheduled = client.list_articles(status="scheduled", limit=20)
        if scheduled["items"]:
            for item in scheduled["items"]:
                when = item.get("scheduled_publish_at") or "—"
                st.write(f"#{item['id']} · {item['title'][:80]} → **{when[:16]}** UTC")
        else:
            st.caption(
                "Нет запланированных публикаций. Появятся после «Опубликовать выбранные» "
                "(кроме первой — она выходит сразу)."
            )
    except Exception as exc:
        st.warning(str(exc))

    st.divider()
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        if st.button("Опубликовать выбранные", type="primary", disabled=not selected):
            _publish_selected(client, list(selected), reject_remaining=False)

    with c2:
        if st.button("Опубликовать все", disabled=not items):
            _publish_selected(
                client,
                [i["id"] for i in items],
                reject_remaining=False,
            )

    with c3:
        if st.button("Опубликовать выбранные + отклонить остальные", disabled=not selected):
            _publish_selected(client, list(selected), reject_remaining=True)

    with c4:
        if st.button("Отклонить все pending"):
            try:
                result = client.reject_all_pending()
                st.success(f"Отклонено: {result.get('rejected', 0)}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if selected:
        if st.button(f"Отклонить выбранные ({len(selected)})"):
            try:
                result = client.reject_articles(list(selected))
                st.success(f"Отклонено: {result.get('rejected', 0)}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _publish_selected(
    client: ContentFactoryClient | EmbeddedBackend,
    article_ids: list[int],
    *,
    reject_remaining: bool,
) -> None:
    with st.spinner("Публикация..."):
        try:
            result = client.publish_batch(
                article_ids,
                reject_remaining=reject_remaining,
            )
            st.success(
                f"Сразу: {result['published']}, "
                f"в очереди: {result.get('scheduled', 0)}, "
                f"ошибок: {result['failed']}"
            )
            for item in result.get("items", []):
                if item.get("scheduled_at"):
                    st.info(
                        f"#{item['article_id']} запланирована на "
                        f"{item['scheduled_at'][:16]}"
                    )
                elif item["success"]:
                    links = [
                        r.get("post_url")
                        for r in item.get("results", [])
                        if r.get("post_url")
                    ]
                    st.write(f"#{item['article_id']} OK — {', '.join(links) or '—'}")
                else:
                    st.error(f"#{item['article_id']}: {item.get('error')}")
            if reject_remaining:
                st.caption("Остальные pending отклонены.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def page_catalog() -> None:
    st.header("Каталог статей")
    client = get_client()

    source_names = [""]
    try:
        source_names += [s["name"] for s in client.list_sources().get("items", [])]
    except Exception:
        source_names += ["DoctorPiter", "Vademecum"]

    col1, col2, col3 = st.columns(3)
    with col1:
        status = st.selectbox(
            "Статус",
            ["", "new", "pending", "scheduled", "published", "skipped"],
            format_func=lambda x: x or "Все",
        )
    with col2:
        source = st.selectbox(
            "Источник",
            source_names,
            format_func=lambda x: x or "Все",
        )
    with col3:
        search = st.text_input("Поиск по заголовку")

    try:
        data = client.list_articles(
            status=status or None,
            source=source or None,
            search=search or None,
            limit=50,
        )
        st.caption(f"Найдено: {data['total']}")
        for item in data["items"]:
            badge = item["status"]
            st.markdown(f"**#{item['id']}** [{badge}] {item['title']}")
            st.caption(
                f"{item.get('source_name')} · {item['fetched_at'][:10]} · {item['url']}"
            )
    except Exception as exc:
        st.error(str(exc))


def main() -> None:
    init_state()
    page = sidebar()

    if page == "Главная":
        page_home()
    elif page == "Сбор новостей":
        page_ingest()
    elif page == "Согласование":
        page_review()
    elif page == "Каталог":
        page_catalog()


if __name__ == "__main__":
    main()
