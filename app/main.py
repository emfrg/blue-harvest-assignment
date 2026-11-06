from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.database import DATABASE_PATH, create_database_engine, create_session_factory


def create_app(database_path=DATABASE_PATH):
    @asynccontextmanager
    async def lifespan(application):
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
        return {"status": "ok"}

    return application


app = create_app()
