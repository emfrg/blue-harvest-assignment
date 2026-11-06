from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Barrier

import pytest

from app import operations
from app.database import create_database_engine


def synchronize_first_reads(monkeypatch):
    original = operations.check_user
    barrier = Barrier(2)
    first_reads = Queue()
    first_reads.put(True)
    first_reads.put(True)

    def check_user_together(*args):
        original(*args)
        try:
            first_reads.get_nowait()
        except Empty:
            return
        barrier.wait(timeout=10)

    monkeypatch.setattr(operations, "check_user", check_user_together)


@pytest.mark.parametrize("same_key", [True, False])
def test_competing_submissions_save_one_request(api_client, monkeypatch, same_key):
    synchronize_first_reads(monkeypatch)

    def send(key):
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
    assert sorted(response.status_code for response in responses) == (
        [200, 201] if same_key else [201, 409]
    )
    saved = api_client.get(
        "/applications/1/requests", headers={"X-User-Id": "1"}
    ).json()
    assert len(saved["requests"]) == 1
    if same_key:
        assert responses[0].json() == responses[1].json()


def test_competing_decisions_preserve_one_outcome(api_client, monkeypatch):
    created = api_client.post(
        "/requests",
        headers={"X-User-Id": "1", "Idempotency-Key": "first"},
        json={"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"},
    ).json()
    synchronize_first_reads(monkeypatch)

    def send(decision):
        user_id, outcome = decision
        return api_client.post(
            f"/requests/{created['id']}/decision",
            headers={"X-User-Id": str(user_id)},
            json={"outcome": outcome},
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(send, [(3, "APPROVED"), (4, "DECLINED")]))
    assert sorted(response.status_code for response in responses) == [200, 409]
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
    engine = create_database_engine(api_database)
    headers = {"X-User-Id": "1", "Idempotency-Key": "first"}
    body = {"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"}
    try:
        with engine.begin() as connection:
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
