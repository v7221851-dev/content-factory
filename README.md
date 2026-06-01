# Content Factory

Микросервис сбора health-новостей (RSS) и публикации в VK и Telegram с панелью согласования.

## Локальный запуск

```bash
cd content-factory
cp .env.example .env   # заполните ключи
pip install -r requirements-api.txt

# Вариант A: панель без отдельного API (рекомендуется локально)
CONTENT_FACTORY_MODE=embedded PYTHONPATH=. python3 scripts/run_admin.py

# Вариант B: API + панель (нужен requirements-api.txt)
PYTHONPATH=. python3 src/main.py          # :8090
PYTHONPATH=. python3 scripts/run_admin.py  # :8501
```

## Streamlit Cloud

1. Создайте репозиторий на GitHub и запушьте `content-factory/`.
2. [share.streamlit.io](https://share.streamlit.io) → **New app**:
   - **Repository:** ваш репо
   - **Main file path:** `streamlit_app.py`
   - **Python version:** `3.11` (Advanced settings)
   - **Branch:** `main`
3. **Settings → Secrets** — вставьте содержимое `.streamlit/secrets.toml.example`, заполните ключи VK/Telegram.
4. Deploy.

На Streamlit Cloud используется режим **embedded** (всё в одном процессе, без FastAPI).

> **База данных:** SQLite на Streamlit Cloud сбрасывается при перезапуске. Для prod подключите PostgreSQL (`DATABASE_URL`) — например Neon или Supabase.

## Workflow

1. **Сбор новостей** — RSS (DoctorPiter, Vademecum)
2. **Подготовить очередь** — 5 статей на согласование
3. **Согласование** — превью, публикация или отклонение
4. Публикация в VK + Telegram

## API (опционально)

Документация: `http://127.0.0.1:8090/docs`  
Заголовок: `X-API-Key`
# content-factory
