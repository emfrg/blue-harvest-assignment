from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "requests.sqlite3"


def enable_foreign_keys(connection, _connection_record):
    """Enable foreign-key checks on each new SQLite connection. (FR-02)"""
    # SQLite only allows foreign-key checks to be enabled outside a transaction.
    # Temporarily enable autocommit to apply this setting. (FR-02)
    original_autocommit = connection.autocommit
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
        connection.autocommit = original_autocommit


def create_database_engine(database_path=DATABASE_PATH):
    """Create a SQLAlchemy engine for the SQLite database file. (QR-01)"""
    database_path = Path(database_path).resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{database_path}",
        # Keep writes in a transaction until commit or rollback. (QR-01)
        connect_args={"autocommit": False},
    )
    # Run enable_foreign_keys whenever this engine opens a new connection. (FR-02)
    event.listen(engine, "connect", enable_foreign_keys)
    return engine


def create_session_factory(engine):
    """Return a callable that creates sessions for this engine. (QR-01)"""
    return sessionmaker(bind=engine)
