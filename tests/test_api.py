from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.init_db import create_database
from app.main import create_app


def submit(client, key="submission-1", user_id=1, **changes):
    body = {"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"}
    body.update(changes)
    return client.post(
        "/requests",
        headers={"X-User-Id": str(user_id), "Idempotency-Key": key},
        json=body,
    )


def decide(client, request_id, outcome, user_id=3):
    return client.post(
        f"/requests/{request_id}/decision",
        headers={"X-User-Id": str(user_id)},
        json={"outcome": outcome},
    )


def history(client, application_id=1):
    response = client.get(
        f"/applications/{application_id}/requests", headers={"X-User-Id": "1"}
    )
    assert response.status_code == 200
    return response.json()["requests"]


def approval(client):
    response = client.get(
        "/applications/1/approved-discount", headers={"X-User-Id": "1"}
    )
    assert response.status_code == 200
    return response.json()["approved_discount"]


def test_submission_records_original_details_and_can_be_read(api_client):
    before = datetime.now(UTC)
    response = submit(api_client)
    after = datetime.now(UTC)
    assert response.status_code == 201
    request = response.json()
    assert request == {
        "id": request["id"],
        "application_id": 1,
        "discount_bps": 25,
        "reason": "Competitive offer",
        "submitted_by": 1,
        "submitted_at": request["submitted_at"],
        "status": "PENDING",
        "retry_key": "submission-1",
        "reviewer_id": None,
        "decided_at": None,
    }
    assert request["id"] > 0
    assert before <= datetime.fromisoformat(request["submitted_at"]) <= after
    for user_id in (1, 3):
        saved = api_client.get(
            f"/requests/{request['id']}", headers={"X-User-Id": str(user_id)}
        )
        assert saved.status_code == 200
        assert saved.json() == request


@pytest.mark.parametrize(
    "changes",
    [
        {"discount_bps": 0},
        {"discount_bps": -1},
        {"discount_bps": 2.5},
        {"discount_bps": 25.0},
        {"discount_bps": True},
        {"discount_bps": "25"},
        {"discount_bps": 9223372036854775808},
        {"reason": ""},
        {"reason": " \t\n"},
        {"reason": 25},
        {"reason": None},
        {"application_id": True},
        {"application_id": "1"},
        {"application_id": 0},
        {"submitted_by": 3},
        {"status": "APPROVED"},
    ],
)
def test_invalid_submission_saves_nothing_and_does_not_reserve_key(api_client, changes):
    response = submit(api_client, **changes)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert history(api_client) == []
    assert submit(api_client).status_code == 201


@pytest.mark.parametrize("missing_field", ["application_id", "discount_bps", "reason"])
def test_submission_requires_all_fields(api_client, missing_field):
    body = {"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"}
    del body[missing_field]
    response = api_client.post(
        "/requests", headers={"X-User-Id": "1", "Idempotency-Key": "key"}, json=body
    )
    assert response.status_code == 422
    assert history(api_client) == []


@pytest.mark.parametrize("key", [None, "", "   "])
def test_submission_requires_nonblank_key(api_client, key):
    headers = {"X-User-Id": "1"}
    if key is not None:
        headers["Idempotency-Key"] = key
    response = api_client.post(
        "/requests",
        headers=headers,
        json={"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"},
    )
    assert response.status_code == 422
    assert history(api_client) == []


def test_malformed_json_is_rejected(api_client):
    response = api_client.post(
        "/requests",
        headers={
            "X-User-Id": "1",
            "Idempotency-Key": "key",
            "Content-Type": "application/json",
        },
        content="{",
    )
    assert response.status_code == 422
    assert history(api_client) == []


@pytest.mark.parametrize(
    "user_id, expected", [(None, 422), ("bad", 422), ("0", 422), ("999", 403)]
)
def test_identity_is_required_for_every_mortgage_operation(
    api_client, user_id, expected
):
    headers = {"Idempotency-Key": "key"}
    if user_id is not None:
        headers["X-User-Id"] = user_id
    calls = [
        (
            "POST", "/requests",
            {"application_id": 1, "discount_bps": 25, "reason": "Offer"},
        ),
        ("GET", "/requests/1", None),
        ("POST", "/requests/1/decision", {"outcome": "APPROVED"}),
        ("GET", "/applications/1/requests", None),
        ("GET", "/applications/1/approved-discount", None),
    ]
    for method, path, body in calls:
        response = api_client.request(method, path, headers=headers, json=body)
        assert response.status_code == expected
    assert history(api_client) == []


def test_roles_cannot_submit_or_decide_for_each_other(api_client):
    assert submit(api_client, user_id=3).status_code == 403
    original = submit(api_client).json()
    assert decide(api_client, original["id"], "APPROVED", user_id=1).status_code == 403
    assert history(api_client) == [original]
    assert decide(api_client, 999, "APPROVED", user_id=1).status_code == 403


def test_unknown_records_are_distinct_from_empty_history_and_no_approval(api_client):
    assert history(api_client) == []
    assert approval(api_client) is None
    for path in (
        "/requests/999",
        "/applications/999/requests",
        "/applications/999/approved-discount",
    ):
        assert api_client.get(path, headers={"X-User-Id": "1"}).status_code == 404
    assert decide(api_client, 999, "APPROVED").status_code == 404
    assert submit(api_client, application_id=999).status_code == 404
    assert submit(api_client).status_code == 201


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_decision_records_reviewer_and_time_and_cannot_be_replaced(api_client, outcome):
    original = submit(api_client).json()
    before = datetime.now(UTC)
    response = decide(api_client, original["id"], outcome)
    after = datetime.now(UTC)
    assert response.status_code == 200
    decided = response.json()
    expected = dict(original)
    expected.update(status=outcome, reviewer_id=3, decided_at=decided["decided_at"])
    assert decided == expected
    assert before <= datetime.fromisoformat(decided["decided_at"]) <= after
    for another_outcome in ("APPROVED", "DECLINED"):
        repeated = decide(api_client, original["id"], another_outcome, user_id=4)
        assert repeated.status_code == 409
    assert history(api_client) == [decided]
    saved = api_client.get(f"/requests/{original['id']}", headers={"X-User-Id": "1"})
    assert saved.json() == decided
    expected_approval = {"request_id": original["id"], "discount_bps": 25}
    assert approval(api_client) == (
        expected_approval if outcome == "APPROVED" else None
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"outcome": "PENDING"},
        {"outcome": "approved"},
        {"outcome": "APPROVED", "discount_bps": 40},
        {"outcome": "APPROVED", "reviewer_id": 4},
    ],
)
def test_invalid_decision_does_not_change_request(api_client, body):
    original = submit(api_client).json()
    response = api_client.post(
        f"/requests/{original['id']}/decision", headers={"X-User-Id": "3"}, json=body
    )
    assert response.status_code == 422
    assert history(api_client) == [original]


@pytest.mark.parametrize("outcome", [None, "APPROVED", "DECLINED"])
def test_submitted_requests_cannot_be_edited_or_deleted(api_client, outcome):
    original = submit(api_client).json()
    if outcome is not None:
        original = decide(api_client, original["id"], outcome).json()
    for method in ("PUT", "PATCH", "DELETE"):
        response = api_client.request(
            method,
            f"/requests/{original['id']}",
            headers={"X-User-Id": "1"},
            json={"discount_bps": 40},
        )
        assert response.status_code == 405
    assert history(api_client) == [original]


def test_changed_request_needs_decline_then_new_submission(api_client):
    first = submit(api_client).json()
    assert submit(api_client, key="second", user_id=2).status_code == 409
    declined = decide(api_client, first["id"], "DECLINED").json()
    response = submit(api_client, key="second", user_id=2, discount_bps=40)
    assert response.status_code == 201
    second = response.json()
    assert second["id"] != first["id"]
    assert second["status"] == "PENDING"
    assert history(api_client) == [declined, second]


def test_replacement_preserves_previous_approval_until_new_approval(api_client):
    first = submit(api_client).json()
    approved = decide(api_client, first["id"], "APPROVED").json()
    first_approval = {"request_id": first["id"], "discount_bps": 25}
    second = submit(api_client, key="second", discount_bps=40).json()
    assert approval(api_client) == first_approval
    declined = decide(api_client, second["id"], "DECLINED").json()
    assert approval(api_client) == first_approval
    third = submit(api_client, key="third", discount_bps=40).json()
    replacement = decide(api_client, third["id"], "APPROVED").json()
    assert approval(api_client) == {"request_id": third["id"], "discount_bps": 40}
    assert history(api_client) == [approved, declined, replacement]


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_matching_retry_returns_current_state_even_when_later_request_is_pending(
    api_client, outcome
):
    first = submit(api_client).json()
    pending_retry = submit(api_client)
    assert pending_retry.status_code == 200
    assert pending_retry.json() == first
    decided = decide(api_client, first["id"], outcome).json()
    second = submit(api_client, key="second").json()
    repeated = submit(api_client)
    assert repeated.status_code == 200
    assert repeated.json() == decided
    assert history(api_client) == [decided, second]


@pytest.mark.parametrize(
    "changes",
    [{"application_id": 2}, {"discount_bps": 40}, {"reason": "Different offer"}],
)
def test_same_key_with_different_details_conflicts_before_and_after_decision(
    api_client, changes
):
    first = submit(api_client).json()
    assert submit(api_client, **changes).status_code == 409
    decided = decide(api_client, first["id"], "APPROVED").json()
    assert submit(api_client, **changes).status_code == 409
    assert history(api_client) == [decided]


def test_retry_key_is_scoped_to_user_and_reason_is_compared_exactly(api_client):
    first = submit(api_client, reason=" Offer ").json()
    assert first["reason"] == " Offer "
    assert submit(api_client, reason="Offer").status_code == 409
    assert submit(api_client, reason=" offer ").status_code == 409
    assert submit(api_client, reason=" Offer ").json() == first
    second = submit(api_client, user_id=2, application_id=2)
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_restart_preserves_decision_history_and_retry_mapping(api_database):
    with TestClient(create_app(api_database)) as client:
        first = submit(client).json()
        decided = decide(client, first["id"], "APPROVED").json()
        second = submit(client, key="second").json()
    with TestClient(create_app(api_database)) as client:
        assert history(client) == [decided, second]
        assert approval(client) == {"request_id": first["id"], "discount_bps": 25}
        repeated = submit(client)
        assert repeated.status_code == 200
        assert repeated.json() == decided


def test_initialisation_can_repeat_without_resetting_requests(api_client, api_database):
    original = submit(api_client).json()
    create_database(api_database)
    assert history(api_client) == [original]


def test_public_docs_describe_inputs_outputs_and_errors(api_client):
    assert api_client.get("/health").json() == {"status": "ok"}
    assert api_client.get("/docs").status_code == 200
    response = api_client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    paths = schema["paths"]
    assert set(paths) == {
        "/health",
        "/requests",
        "/requests/{request_id}",
        "/requests/{request_id}/decision",
        "/applications/{application_id}/requests",
        "/applications/{application_id}/approved-discount",
    }
    submission = paths["/requests"]["post"]
    assert {"200", "201", "403", "404", "409", "422", "503"} <= set(
        submission["responses"]
    )
    assert {parameter["name"] for parameter in submission["parameters"]} == {
        "X-User-Id", "Idempotency-Key",
    }
    models = schema["components"]["schemas"]
    assert set(models["Submission"]["required"]) == {
        "application_id", "discount_bps", "reason",
    }
    assert models["Submission"]["additionalProperties"] is False
    assert models["Decision"]["properties"]["outcome"]["enum"] == [
        "APPROVED", "DECLINED",
    ]
    assert set(models["RequestDetails"]["required"]) == {
        "id", "application_id", "discount_bps", "reason", "submitted_by",
        "submitted_at", "status", "retry_key", "reviewer_id", "decided_at"
    }
