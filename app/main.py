from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.database import DATABASE_PATH, create_database_engine, create_session_factory


def create_app(database_path=DATABASE_PATH):
    """Create an API instance using the selected SQLite file. (QR-01)"""
    @asynccontextmanager
    async def lifespan(application):
        """Provide a session factory and close connections at shutdown. (QR-01)"""
        engine = create_database_engine(database_path)
        application.state.sessions = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(lifespan=lifespan)
    application.include_router(router)

    @application.get("/health")
    def health():
        """Return the API health status without requiring user identity. (FR-03)"""
        return {"status": "ok"}

    return application


app = create_app()
