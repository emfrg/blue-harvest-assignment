from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from app.api import demo_router, router
from app.database import DATABASE_PATH, create_database_engine, create_session_factory


def create_app(database_path: str | Path = DATABASE_PATH) -> FastAPI:
    """Create an API instance using the selected SQLite file."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        """Provide a session factory and close connections at shutdown."""
        engine = create_database_engine(database_path)
        application.state.sessions = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(lifespan=lifespan)
    application.include_router(router)
    application.include_router(demo_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        """Confirm that the API is responding."""
        return {"status": "ok"}

    return application


app = create_app()
