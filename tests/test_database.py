"""Exercise real SQLite connections and transactions using small test tables.

The database_engine fixture supplies parent and child tables so these checks
can isolate connection setup, commits, rollbacks and foreign-key enforcement.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from app.database import create_session_factory


def test_database_connection(database_engine: Engine) -> None:
    """Check that a connection can execute SQL and return its result.

    SELECT 1 asks SQLite to return the number 1; no table data is needed.
    """
    with database_engine.connect() as connection:
        result = connection.exec_driver_sql("SELECT 1").scalar_one()
        assert result == 1


def test_committed_data_survives_reconnection(database_engine: Engine) -> None:
    """Check that a committed row can be read through a new connection.

    Save a parent row, close the pooled connection, then read the row again
    using the same database file.
    """
    sessions = create_session_factory(database_engine)
    with sessions.begin() as session:
        session.execute(text("INSERT INTO parents (id) VALUES (1)"))

    database_engine.dispose()

    with sessions.begin() as session:
        result = session.execute(text("SELECT id FROM parents")).scalar_one()
        assert result == 1


def test_failed_transaction_is_rolled_back(database_engine: Engine) -> None:
    """Check that an error cancels writes made in the transaction.

    Insert a parent and deliberately raise an exception before commit.
    A new transaction must find the table empty.
    """
    sessions = create_session_factory(database_engine)
    with pytest.raises(RuntimeError, match="cancel transaction"):
        with sessions.begin() as session:
            session.execute(text("INSERT INTO parents (id) VALUES (1)"))
            raise RuntimeError("cancel transaction")

    with sessions.begin() as session:
        count = session.execute(text("SELECT COUNT(*) FROM parents")).scalar_one()
        assert count == 0


def test_foreign_key_rejects_missing_parent(database_engine: Engine) -> None:
    """Check that new connections enforce foreign-key constraints.

    Try to save a child whose parent does not exist. SQLite must raise an
    integrity error, and the children table must stay empty.
    """
    # The next operation must open a new connection with foreign-key checks enabled.
    database_engine.dispose()
    sessions = create_session_factory(database_engine)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with sessions.begin() as session:
            session.execute(
                text("INSERT INTO children (id, parent_id) VALUES (1, 999)")
            )

    with sessions.begin() as session:
        count = session.execute(text("SELECT COUNT(*) FROM children")).scalar_one()
        assert count == 0
