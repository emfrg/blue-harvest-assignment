from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import create_database_engine, create_session_factory
from app.models import Base, DiscountRequest, MortgageApplication, User


@pytest.fixture
def model_engine(tmp_path):
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
    sessions = create_session_factory(model_engine)
    before = datetime.now(UTC)
    with sessions.begin() as session:
        session.add(example_request())
    after = datetime.now(UTC)

    # Test persistence.
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
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(example_request())

    # Reject a second saved request with the same user and key.
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
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(example_request())

    # This application already has a pending request.
    with pytest.raises(IntegrityError, match="requests.application_id"):
        with sessions.begin() as session:
            session.add(example_request(retry_key="submission-2"))

    with sessions.begin() as session:
        request = session.scalars(select(DiscountRequest)).one()
        assert request.retry_key == "submission-1"


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_retry_key_remains_reserved_after_decision(model_engine, outcome):
    sessions = create_session_factory(model_engine)
    with sessions.begin() as session:
        session.add(
            example_request(
                status=outcome,
                reviewer_id=3,
                decided_at="2026-11-05T14:00:00.000000+00:00",
            )
        )
    # Reject another record using the decided request's user and key.
    with pytest.raises(
        IntegrityError, match="requests.submitted_by, requests.retry_key"
    ):
        with sessions.begin() as session:
            session.add(example_request(application_id=2))


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_new_request_keeps_previous_request_and_decision(model_engine, outcome):
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
        # Discounts must be positive whole numbers.
        ({"discount_bps": 0}, "positive_whole_discount"),
        ({"discount_bps": -1}, "positive_whole_discount"),
        ({"discount_bps": 2.5}, "positive_whole_discount"),
        ({"status": "UNKNOWN"}, "valid_request_status"),
        # Pending: no reviewer/time. Approved or declined: both required.
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
    sessions = create_session_factory(model_engine)
    with pytest.raises(IntegrityError, match=error):
        with sessions.begin() as session:
            session.add(example_request(**changes))

    with sessions.begin() as session:
        assert session.scalars(select(DiscountRequest)).all() == []


def test_database_rejects_unknown_user_role(model_engine):
    sessions = create_session_factory(model_engine)
    with pytest.raises(IntegrityError, match="valid_user_role"):
        with sessions.begin() as session:
            session.add(User(id=4, role="UNKNOWN"))
