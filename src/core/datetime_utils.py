from datetime import datetime, timezone


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Приводит datetime к UTC (SQLite часто возвращает naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
