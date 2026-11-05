import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import create_session_factory


def test_database_connection(database_engine):
    with database_engine.connect() as connection:
        result = connection.exec_driver_sql("SELECT 1").scalar_one()
        assert result == 1


def test_committed_data_survives_reconnection(database_engine):
    sessions = create_session_factory(database_engine)
    with sessions.begin() as session:
        session.execute(text("INSERT INTO parents (id) VALUES (1)"))

    database_engine.dispose()

    with sessions.begin() as session:
        result = session.execute(text("SELECT id FROM parents")).scalar_one()
        assert result == 1


def test_failed_transaction_is_rolled_back(database_engine):
    sessions = create_session_factory(database_engine)
    with pytest.raises(RuntimeError, match="cancel transaction"):
        with sessions.begin() as session:
            session.execute(text("INSERT INTO parents (id) VALUES (1)"))
            raise RuntimeError("cancel transaction")

    with sessions.begin() as session:
        count = session.execute(text("SELECT COUNT(*) FROM parents")).scalar_one()
        assert count == 0


def test_foreign_key_rejects_missing_parent(database_engine):
    database_engine.dispose()
    sessions = create_session_factory(database_engine)
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with sessions.begin() as session:
            session.execute(text("INSERT INTO children (id, parent_id) VALUES (1, 999)"))

    with sessions.begin() as session:
        count = session.execute(text("SELECT COUNT(*) FROM children")).scalar_one()
        assert count == 0
