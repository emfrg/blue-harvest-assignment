"""Check stored values and constraints by writing directly through SQLAlchemy.

Invalid records reach SQLite without passing through API validation. Each test
uses its own database, created by model_engine below.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import create_database_engine, create_session_factory
from app.models import Base, DiscountRequest, MortgageApplication, User


@pytest.fixture
def model_engine(tmp_path):
    """Provide a temporary database for direct model tests.

    Seed two mortgage applications, two relationship managers and one reviewer.
    Each test gets a separate SQLite file; close pooled connections afterward.
    """
    engine = create_database_engine(tmp_path / "models.sqlite3")
    try:
        Base.metadata.create_all(engine)
        sessions = create_session_factory(engine)
        with sessions.begin() as session:
            session.add_all([MortgageApplication(id=1), MortgageApplication(id=2)])
            session.add_all(
                [
                    User(id=1, role="RELATIONSHIP_MANAGER"),
                    User(id=2, role="RELATIONSHIP_MANAGER"),
                    User(id=3, role="REVIEWER"),
                ]
            )
        yield engine
    finally:
        engine.dispose()


def example_request(**changes):
    """Build an unsaved request with default fields overridden by changes."""
    fields = {
        "application_id": 1,
        "discount_bps": 25,
        "reason": "Competitive offer",
        "submitted_by": 1,
        "retry_key": "submission-1",
    }
    fields.update(changes)
    return DiscountRequest(**fields)


def test_request_stores_submitted_fields_and_defaults(model_engine):
    """Check the saved submission fields and model defaults.

    Read the row in a new session. Expect the submitted values, a generated
    ID, PENDING status and no decision. The submission time must be UTC and
    fall between the times captured around the save.
    """
    sessions = create_session_factory(model_engine)
    before = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(example_request())
    after = datetime.now(UTC)

    with sessions.begin() as session:
        request = session.scalars(select(DiscountRequest)).one()
        assert request.id > 0
        assert request.application_id == 1
        assert request.discount_bps == 25
        assert request.reason == "Competitive offer"
        assert request.submitted_by == 1
        assert request.retry_key == "submission-1"
        assert request.status == "PENDING"
        assert request.reviewer_id is None
        assert request.decided_at is None
        assert request.submitted_at.endswith("+00:00")
        assert before <= datetime.fromisoformat(request.submitted_at) <= after


def test_retry_key_is_unique_per_user(model_engine):
    """Check that a submission key is unique within one user's requests.

    Saving the same user's key for a different application must fail.
    Another user can use that key for their own request.
    """
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(example_request())

    # Reject a second saved request with the same user and key. (FR-14)
    with pytest.raises(
        IntegrityError, match="requests.submitted_by, requests.retry_key"
    ):
        with sessions.begin() as session:
            session.add(example_request(application_id=2))

    with sessions.begin() as session:
        session.add(example_request(application_id=2, submitted_by=2))

    with sessions.begin() as session:
        requests = session.scalars(select(DiscountRequest)).all()
        assert len(requests) == 2


def test_second_pending_request_is_rejected(model_engine):
    """Check that an application cannot have two pending requests.

    Save a request, then try another with a different submission key.
    SQLite must reject the second insert and retain only the original request.
    """
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(example_request())

    # This application already has a pending request. (FR-05)
    with pytest.raises(IntegrityError, match="requests.application_id"):
        with sessions.begin() as session:
            session.add(example_request(retry_key="submission-2"))

    with sessions.begin() as session:
        request = session.scalars(select(DiscountRequest)).one()
        assert request.retry_key == "submission-1"


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_retry_key_remains_reserved_after_decision(model_engine, outcome):
    """Check that a decision does not make a user's submission key reusable.

    Start with an approved or declined request. An insert using its user
    and submission key for another application must fail.
    """
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(
            example_request(
                status=outcome,
                reviewer_id=3,
                decided_at="2026-11-05T14:00:00.000000+00:00",
            )
        )
    # Reject another record using the decided request's user and key. (FR-14)
    with pytest.raises(
        IntegrityError, match="requests.submitted_by, requests.retry_key"
    ):
        with sessions.begin() as session:
            session.add(example_request(application_id=2))


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_new_request_keeps_previous_request_and_decision(model_engine, outcome):
    """Check that a new request leaves the previous decision intact.

    Approve or decline the first request, then save another pending request
    for the same application. Both rows must exist, and the first row must
    keep its ID, outcome, reviewer and decision time.
    """
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(example_request())
    # Adding a new request must preserve the earlier approval or decline.
    decision_time = "2026-11-05T14:00:00.000000+00:00"
    with sessions.begin() as session:
        request = session.scalars(select(DiscountRequest)).one()
        original_id = request.id
        request.status = outcome
        request.reviewer_id = 3
        request.decided_at = decision_time

    with sessions.begin() as session:
        session.add(example_request(retry_key="submission-2"))

    with sessions.begin() as session:
        requests = session.scalars(
            select(DiscountRequest).order_by(DiscountRequest.id)
        ).all()
        assert len(requests) == 2
        assert requests[0].id == original_id
        assert requests[0].status == outcome
        assert requests[0].reviewer_id == 3
        assert requests[0].decided_at == decision_time
        assert requests[1].status == "PENDING"


@pytest.mark.parametrize(
    "changes, error",
    [
        # Discounts must be positive whole numbers. (FR-02)
        ({"discount_bps": 0}, "positive_whole_discount"),
        ({"discount_bps": -1}, "positive_whole_discount"),
        ({"discount_bps": 2.5}, "positive_whole_discount"),
        ({"status": "UNKNOWN"}, "valid_request_status"),
        # Pending requests have no reviewer or decision time.
        # Approved and declined requests must have both. (FR-09)
        ({"reviewer_id": 3}, "decision_matches_status"),
        ({"decided_at": "2026-11-05T14:00:00+00:00"}, "decision_matches_status"),
        ({"status": "APPROVED", "reviewer_id": 3}, "decision_matches_status"),
        (
            {"status": "DECLINED", "decided_at": "2026-11-05T14:00:00+00:00"},
            "decision_matches_status",
        ),
        # Referenced applications and users must exist.
        ({"application_id": 999}, "FOREIGN KEY constraint failed"),
        ({"submitted_by": 999}, "FOREIGN KEY constraint failed"),
        (
            {
                "status": "APPROVED",
                "reviewer_id": 999,
                "decided_at": "2026-11-05T14:00:00+00:00",
            },
            "FOREIGN KEY constraint failed",
        ),
    ],
)
def test_database_rejects_invalid_request_records(model_engine, changes, error):
    """Check that SQLite rejects records which violate the model constraints.

    Each case changes fields on an otherwise valid request. Expect the named
    constraint to reject it, and confirm that no request row was saved.
    """
    sessions = create_session_factory(model_engine)
    with pytest.raises(IntegrityError, match=error):
        with sessions.begin() as session:
            session.add(example_request(**changes))

    with sessions.begin() as session:
        assert session.scalars(select(DiscountRequest)).all() == []


def test_database_rejects_unknown_user_role(model_engine):
    """Check that SQLite rejects a user whose role is UNKNOWN."""
    sessions = create_session_factory(model_engine)
    with pytest.raises(IntegrityError, match="valid_user_role"):
        with sessions.begin() as session:
            session.add(User(id=4, role="UNKNOWN"))
