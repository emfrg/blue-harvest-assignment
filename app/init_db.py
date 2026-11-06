from app.database import DATABASE_PATH, create_database_engine, create_session_factory
from app.models import Base, MortgageApplication, User


def create_database(database_path=DATABASE_PATH):
    """Set up the database tables and sample mortgage applications and users."""
    engine = create_database_engine(database_path)
    try:
        Base.metadata.create_all(engine)
        sessions = create_session_factory(engine)
        # Insert the sample applications and users if they do not already exist.
        with sessions.begin() as session:
            for application_id in (1, 2):
                if session.get(MortgageApplication, application_id) is None:
                    session.add(MortgageApplication(id=application_id))
            for user_id, role in (
                (1, "RELATIONSHIP_MANAGER"),
                (2, "RELATIONSHIP_MANAGER"),
                (3, "REVIEWER"),
                (4, "REVIEWER"),
            ):
                if session.get(User, user_id) is None:
                    session.add(User(id=user_id, role=role))
    finally:
        engine.dispose()
    print(f"Database ready: {engine.url.database}")


if __name__ == "__main__":
    create_database()
