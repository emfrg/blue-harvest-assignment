import pytest
from fastapi.testclient import TestClient

from app.database import create_database_engine
from app.init_db import create_database
from app.main import create_app


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


@pytest.fixture
def api_database(tmp_path):
    path = tmp_path / "api.sqlite3"
    create_database(path)
    return path


@pytest.fixture
def api_client(api_database):
    with TestClient(create_app(api_database)) as client:
        yield client
