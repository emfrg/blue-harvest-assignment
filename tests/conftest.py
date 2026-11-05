import pytest

from app.database import create_database_engine


@pytest.fixture
def database_engine(tmp_path):
    # Create a temporary SQLite database for testing.
    engine = create_database_engine(tmp_path / "test.sqlite3")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE parents (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE children ("
                "id INTEGER PRIMARY KEY, "
                "parent_id INTEGER NOT NULL REFERENCES parents(id))"
            )
        yield engine
    finally:
        engine.dispose()
