from app.database import DATABASE_PATH, create_database_engine
from app.models import Base


def create_database():
    engine = create_database_engine()
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    print(f"Database ready: {DATABASE_PATH}")


if __name__ == "__main__":
    create_database()
