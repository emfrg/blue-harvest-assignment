from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "requests.sqlite3"


def enable_foreign_keys(connection, _connection_record):
    """Enable foreign-key checks on each new SQLite connection. (FR-02)"""
    # SQLite requires this setting to be changed outside a transaction.
    original_autocommit = connection.autocommit
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        # Reject references to records that do not exist. (FR-02, FR-03)
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
        connection.autocommit = original_autocommit


def create_database_engine(database_path=DATABASE_PATH):
    """Configure SQLite transactions and foreign-key checks. (QR-01, FR-02)"""
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"autocommit": False},
    )
    event.listen(engine, "connect", enable_foreign_keys)
    return engine


def create_session_factory(engine):
    """Return a callable that creates sessions for this engine. (QR-01)"""
    return sessionmaker(bind=engine)
