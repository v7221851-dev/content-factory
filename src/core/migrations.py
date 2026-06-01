import sqlalchemy as sa
from sqlalchemy.engine import Connection

from src.core.db import Base, engine


def _add_image_url_column(connection: Connection) -> None:
    inspector = sa.inspect(connection)
    if "raw_articles" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("raw_articles")}
    if "image_url" not in columns:
        connection.execute(
            sa.text("ALTER TABLE raw_articles ADD COLUMN image_url VARCHAR(2048)")
        )
    if "scheduled_publish_at" not in columns:
        connection.execute(
            sa.text("ALTER TABLE raw_articles ADD COLUMN scheduled_publish_at DATETIME")
        )
    if "scheduled_platforms" not in columns:
        connection.execute(
            sa.text("ALTER TABLE raw_articles ADD COLUMN scheduled_platforms VARCHAR(128)")
        )


async def ensure_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_image_url_column)
