# Деплой Content Factory на Streamlit Cloud

## Шаг 1 — GitHub

```bash
cd content-factory
git init -b main
git add -A
git status   # убедитесь: .env и *.db НЕ в списке
git commit -m "Content Factory: RSS ingest, VK/Telegram publish, Streamlit admin"
```

Создайте репозиторий: [github.com/new](https://github.com/new) → имя `content-factory`, **без** README.

```bash
git remote add origin https://github.com/ВАШ_USERNAME/content-factory.git
git push -u origin main
```

## Шаг 2 — Streamlit Cloud

1. Откройте [share.streamlit.io](https://share.streamlit.io) → **Sign in with GitHub**
2. **Create app**
   - **Repository:** `ВАШ_USERNAME/content-factory`
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py`
   - **Python version:** `3.11` (Advanced settings — обязательно, иначе Cloud может взять 3.13+)
3. **Advanced settings → Secrets** — вставьте блок ниже (значения из локального `.env`):

```toml
CONTENT_FACTORY_MODE = "embedded"
CONTENT_FACTORY_API_KEY = "смените-на-секретный-ключ"

DATABASE_URL = "sqlite+aiosqlite:///./content_factory.db"

MDSA_APP_URL = "https://mdsa.tech"
POST_PREVIEW_MAX_CHARS = 900
POST_MAX_TOTAL_CHARS = 1024
DAILY_REVIEW_LIMIT = 5
DEFAULT_PUBLISH_PLATFORMS = "vk,telegram"
DAILY_PREPARE_ENABLED = "true"
DAILY_PREPARE_HOUR = 8
DAILY_PREPARE_MINUTE = 0
RSS_FETCH_INTERVAL_MINUTES = 0
PUBLISH_INTERVAL_MINUTES = 30

VK_GROUP_ID = "ваш_id"
VK_ACCESS_TOKEN = "ваш_токен"
VK_USER_ACCESS_TOKEN = "ваш_user_токен"

TELEGRAM_BOT_TOKEN = "ваш_бот"
TELEGRAM_CHANNEL_ID = "@mdsahealth"
```

4. **Deploy** → дождитесь зелёного статуса

URL будет вида: `https://content-factory-xxxxx.streamlit.app`

## Шаг 3 — Проверка после деплоя

- Главная → платформы `vk, telegram` в статусе OK
- Сбор новостей → источники видны, RSS собирается
- Согласование → публикация тестовой статьи

## База данных (важно)

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| **SQLite** (по умолчанию) | Просто | Данные **сбрасываются** при redeploy |
| **PostgreSQL (Neon)** | Добавьте `asyncpg` в `requirements.txt` перед deploy |

### PostgreSQL через Neon (рекомендуется для prod)

1. [neon.tech](https://neon.tech) → создайте БД
2. Скопируйте connection string
3. В Streamlit Secrets замените:

```toml
DATABASE_URL = "postgresql+asyncpg://user:pass@host/dbname?ssl=require"
```

4. Добавьте строку `asyncpg>=0.30.0` в `requirements.txt` и сделайте `git push`

## Если сборка падает (installer non-zero exit code)

1. **Manage app → Logs** — найдите строку с `ERROR` / `Could not find` (это точная причина).
2. Убедитесь, что в Advanced settings выбран **Python 3.11**.
3. `requirements.txt` должен содержать `streamlit` (Cloud собирает venv только из этого файла).
4. После `git push` нажмите **Reboot app** или дождитесь автопересборки (1–3 мин).

## Безопасность

- **Не коммитьте** `.env` — он в `.gitignore`
- Смените `CONTENT_FACTORY_API_KEY` на случайную строку
- VK/Telegram токены — только в Streamlit Secrets

## Обновление после изменений в коде

```bash
git add -A && git commit -m "описание" && git push
```

Streamlit Cloud пересоберёт приложение автоматически (1–3 мин).
