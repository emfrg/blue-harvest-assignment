from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.database import create_database_engine
from app.init_db import create_database
from app.main import create_app


@pytest.fixture
def database_engine(tmp_path: Path) -> Iterator[Engine]:
    """Provide an engine for temporary tables used by database tests.

    Each test gets a separate SQLite file with parent and child tables.
    Close pooled connections after the test, including when it fails.
    """
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
def api_database(tmp_path: Path) -> Path:
    """Create the API's tables and sample records in a temporary SQLite file.

    Returns:
        The path to the test database. The api_client fixture gives this path
        to create_app so API calls use this file instead of data/requests.sqlite3.
    """
    path = tmp_path / "api.sqlite3"
    create_database(path)
    return path


@pytest.fixture
def api_client(api_database: Path) -> Iterator[TestClient]:
    """Provide an API client for the test's temporary SQLite database.

    The client calls FastAPI directly without starting a server. Its context
    manager runs the application's startup and shutdown code.
    """
    with TestClient(create_app(api_database)) as client:
        yield client
