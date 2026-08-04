from sqlalchemy import text

from app.database import engine


def test_sqlite_connection_pragmas_are_enabled() -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() > 0
        assert connection.execute(text("PRAGMA journal_mode")).scalar().lower() in {
            "wal",
            "memory",
        }
