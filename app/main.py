from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.database import DATABASE_PATH, create_database_engine, create_session_factory


def create_app(database_path=DATABASE_PATH):
    """Create an API instance using the selected SQLite file."""
    @asynccontextmanager
    async def lifespan(application):
        """Provide a session factory and close connections at shutdown."""
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
        """Confirm that the API is responding."""
        return {"status": "ok"}

    return application


app = create_app()
