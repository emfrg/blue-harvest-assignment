from pathlib import Path

from sqlalchemy import create_engine, event

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "requests.sqlite3"


def enable_foreign_keys(connection, _connection_record):
    # SQLite requires this setting to be changed outside a transaction.
    original_autocommit = connection.autocommit
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")  # enabling foreign key support
    finally:
        cursor.close()
        connection.autocommit = original_autocommit


def create_database_engine(database_path=DATABASE_PATH):
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"autocommit": False},
    )
    event.listen(engine, "connect", enable_foreign_keys)
    return engine
