"""Exercise overlapping API calls and a held SQLite write lock.

The requests share a temporary database. The coordination helper changes when
calls continue, while the real user lookup and database writes still run.
"""

from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Barrier

import pytest

from app import operations
from app.database import create_database_engine


def synchronize_first_reads(monkeypatch):
    """Make the first two operations wait for each other after reading the user.

    Temporarily replace check_user with a wrapper that runs the real lookup.
    The first two calls meet at a barrier, then continue together. Later calls,
    including database retries, do not wait.
    """
    original = operations.check_user
    barrier = Barrier(2)
    # Only two calls may wait at the barrier; a database retry must continue.
    first_reads = Queue()
    first_reads.put(True)
    first_reads.put(True)

    def check_user_together(*args):
        """Check the user and let the first two calls wait for each other."""
        original(*args)
        try:
            first_reads.get_nowait()
        except Empty:
            return
        barrier.wait(timeout=10)

    monkeypatch.setattr(operations, "check_user", check_user_together)


@pytest.mark.parametrize("same_key", [True, False])
def test_competing_submissions_save_one_request(api_client, monkeypatch, same_key):
    """Check that competing submissions leave one stored request.

    Send the same payload twice. With the same key, expect one 201 and one
    200 with identical response bodies. With different keys, expect one 201
    and one 409 because only one request may be pending for the application.
    In both cases, history must contain exactly one request.
    """
    synchronize_first_reads(monkeypatch)

    def send(key):
        """Submit with the chosen key and return the HTTP response."""
        return api_client.post(
            "/requests",
            headers={"X-User-Id": "1", "Idempotency-Key": key},
            json={
                "application_id": 1, "discount_bps": 25, "reason": "Competitive offer"
            },
        )

    keys = ["first", "first" if same_key else "second"]
    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(send, keys))
    # Matching keys must return the same request; distinct keys must conflict.
    # Neither case may create a second pending request. (FR-05, FR-14, QR-02)
    assert sorted(response.status_code for response in responses) == (
        [200, 201] if same_key else [201, 409]
    )
    saved = api_client.get(
        "/applications/1/requests", headers={"X-User-Id": "1"}
    ).json()
    assert len(saved["requests"]) == 1
    if same_key:
        assert responses[0].json() == responses[1].json()


def test_competing_submissions_with_same_key_and_different_discounts(
    api_client, monkeypatch
):
    """Check that a shared key cannot save two different submissions.

    Submit discounts of 25 and 40 at the same time using the same user and
    key. Either may succeed. The other must report conflicting details, and
    history must contain only the successful submission. Retrying each body
    must preserve that result.
    """
    synchronize_first_reads(monkeypatch)

    def send(discount_bps):
        """Submit the chosen discount with the shared user and key."""
        return api_client.post(
            "/requests",
            headers={"X-User-Id": "1", "Idempotency-Key": "shared"},
            json={
                "application_id": 1,
                "discount_bps": discount_bps,
                "reason": "Competitive offer",
            },
        )

    discounts = [25, 40]
    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(send, discounts))
    assert sorted(response.status_code for response in responses) == [201, 409]

    for discount, response in zip(discounts, responses):
        if response.status_code == 201:
            winner = response.json()
            assert winner["discount_bps"] == discount
        else:
            assert response.json() == {
                "detail": "Retry key already used with different details"
            }

    # The key must identify the saved submission, even after both calls finish.
    # Conflicting details must never replace it. (FR-14, FR-15, QR-02)
    for discount in discounts:
        repeated = send(discount)
        if discount == winner["discount_bps"]:
            assert repeated.status_code == 200
            assert repeated.json() == winner
        else:
            assert repeated.status_code == 409
            assert repeated.json() == {
                "detail": "Retry key already used with different details"
            }

    saved = api_client.get(
        "/applications/1/requests", headers={"X-User-Id": "1"}
    )
    assert saved.status_code == 200
    assert saved.json()["requests"] == [winner]


def test_competing_decisions_preserve_one_outcome(api_client, monkeypatch):
    """Check that competing reviewers cannot overwrite each other's decision.

    Send approval and decline for the same pending request. Exactly one call
    must return 200 and the other 409. The saved record must match the
    successful response, including its reviewer. The current approval must
    contain this request's discount only if approval succeeded.
    """
    created = api_client.post(
        "/requests",
        headers={"X-User-Id": "1", "Idempotency-Key": "first"},
        json={"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"},
    ).json()
    synchronize_first_reads(monkeypatch)

    def send(decision):
        """Send a (reviewer ID, outcome) pair and return the HTTP response."""
        user_id, outcome = decision
        return api_client.post(
            f"/requests/{created['id']}/decision",
            headers={"X-User-Id": str(user_id)},
            json={"outcome": outcome},
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(send, [(3, "APPROVED"), (4, "DECLINED")]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    # Either reviewer may finish first. The other decision must not replace
    # the successful call's recorded outcome. (FR-08, QR-02)
    winner = next(
        response.json() for response in responses if response.status_code == 200
    )
    saved = api_client.get(
        f"/requests/{created['id']}", headers={"X-User-Id": "1"}
    ).json()
    assert saved == winner
    assert saved["reviewer_id"] == (3 if saved["status"] == "APPROVED" else 4)
    current = api_client.get(
        "/applications/1/approved-discount", headers={"X-User-Id": "1"}
    ).json()["approved_discount"]
    expected = {"request_id": created["id"], "discount_bps": 25}
    assert current == (expected if saved["status"] == "APPROVED" else None)


def test_busy_database_returns_503_without_reserving_submission_key(
    api_client, api_database
):
    """Check the API's failure and retry behavior when SQLite is locked.

    Hold a SQLite write transaction open while submitting a request. Expect
    503 with the busy message and no saved request. After the lock is released,
    the same key and payload must succeed with 201.
    """
    engine = create_database_engine(api_database)
    headers = {"X-User-Id": "1", "Idempotency-Key": "first"}
    body = {"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"}
    try:
        with engine.begin() as connection:
            # Updating a value to itself acquires a write lock without changing it.
            connection.exec_driver_sql("UPDATE users SET role = role WHERE id = 1")
            response = api_client.post("/requests", headers=headers, json=body)
            assert response.status_code == 503
            assert response.json() == {"detail": "Database busy; try again"}
    finally:
        engine.dispose()
    saved = api_client.get(
        "/applications/1/requests", headers={"X-User-Id": "1"}
    ).json()
    assert saved["requests"] == []
    assert api_client.post("/requests", headers=headers, json=body).status_code == 201
