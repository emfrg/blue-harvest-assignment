"""Exercise HTTP routes, validation and database operations together.

The api_client fixture gives each test a fresh SQLite database with sample
applications and users. Requests run through FastAPI without a separate server.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, Unpack, cast

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from app.init_db import create_database
from app.main import create_app


class SubmissionChanges(TypedDict, total=False):
    """Optional test fields whose values may deliberately violate API rules."""

    application_id: object
    discount_bps: object
    reason: object
    submitted_by: object
    status: object


def submit(
    client: TestClient,
    key: str = "submission-1",
    user_id: int = 1,
    **changes: Unpack[SubmissionChanges],
) -> Response:
    """Send a test submission and return the HTTP response.

    Use the default request fields unless changes supplies replacements.
    The caller can choose the user and key to exercise permissions and retries.
    """
    body: dict[str, object] = {
        "application_id": 1,
        "discount_bps": 25,
        "reason": "Competitive offer",
    }
    body.update(changes)
    return client.post(
        "/requests",
        headers={"X-User-Id": str(user_id), "Idempotency-Key": key},
        json=body,
    )


def decide(
    client: TestClient, request_id: int, outcome: str, user_id: int = 3
) -> Response:
    """Send a decision as the chosen user and return the HTTP response."""
    return client.post(
        f"/requests/{request_id}/decision",
        headers={"X-User-Id": str(user_id)},
        json={"outcome": outcome},
    )


def history(client: TestClient, application_id: int = 1) -> list[dict[str, object]]:
    """Assert a successful history lookup and return its list of requests."""
    response = client.get(
        f"/applications/{application_id}/requests", headers={"X-User-Id": "1"}
    )
    assert response.status_code == 200
    return cast(list[dict[str, object]], response.json()["requests"])


def approval(client: TestClient, application_id: int = 1) -> dict[str, int] | None:
    """Read the application's approval and assert that the call succeeds.

    Returns:
        A dictionary containing request_id and discount_bps, or None when
        the application has no approved request.
    """
    response = client.get(
        f"/applications/{application_id}/approved-discount",
        headers={"X-User-Id": "1"},
    )
    assert response.status_code == 200
    return cast(dict[str, int] | None, response.json()["approved_discount"])


def test_submission_records_original_details_and_can_be_read(
    api_client: TestClient,
) -> None:
    """Check that a manager can create and retrieve a pending request.

    Expect HTTP 201 with the original submission details, a generated ID and
    a submission time within the call. Both a manager and a reviewer must
    retrieve the same record, with no decision recorded.
    """
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
        "reviewer_id": None,
        "decided_at": None,
    }
    assert request["id"] > 0
    assert before <= datetime.fromisoformat(request["submitted_at"]) <= after
    # Reading a request is allowed for either role. (FR-03, FR-10)
    for user_id in (1, 3):
        saved = api_client.get(
            f"/requests/{request['id']}", headers={"X-User-Id": str(user_id)}
        )
        assert saved.status_code == 200
        assert saved.json() == request


@pytest.mark.parametrize(
    "changes",
    [
        # Discounts must be positive JSON integers within SQLite's range. (FR-02)
        {"discount_bps": 0},
        {"discount_bps": -1},
        {"discount_bps": 2.5},
        {"discount_bps": 25.0},
        {"discount_bps": True},
        {"discount_bps": "25"},
        {"discount_bps": 9223372036854775808},
        # Reasons must be non-blank strings.
        {"reason": ""},
        {"reason": " \t\n"},
        {"reason": 25},
        {"reason": None},
        # Application IDs must be positive JSON integers.
        {"application_id": True},
        {"application_id": "1"},
        {"application_id": 0},
        # The service assigns the submitter and initial status.
        {"submitted_by": 3},
        {"status": "APPROVED"},
    ],
)
def test_invalid_submission_saves_nothing_and_does_not_reserve_key(
    api_client: TestClient, changes: SubmissionChanges
) -> None:
    """Check that invalid fields are rejected without consuming the key.

    Cases cover invalid discounts, reasons, application IDs and fields that
    callers must not supply. Expect HTTP 422 and empty history. A valid
    submission with the same key must then succeed.
    """
    response = submit(api_client, **changes)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert history(api_client) == []
    assert submit(api_client).status_code == 201


@pytest.mark.parametrize("missing_field", ["application_id", "discount_bps", "reason"])
def test_submission_requires_all_fields(
    api_client: TestClient, missing_field: str
) -> None:
    """Check that every submission field is mandatory.

    Omit application_id, discount_bps or reason in turn. Each call must return
    422 without saving a request.
    """
    body = {"application_id": 1, "discount_bps": 25, "reason": "Competitive offer"}
    del body[missing_field]
    response = api_client.post(
        "/requests", headers={"X-User-Id": "1", "Idempotency-Key": "key"}, json=body
    )
    assert response.status_code == 422
    assert history(api_client) == []


@pytest.mark.parametrize("key", [None, "", "   "])
def test_submission_requires_nonblank_key(
    api_client: TestClient, key: str | None
) -> None:
    """Check that a submission needs a non-blank Idempotency-Key header.

    Try a missing, empty or whitespace-only key. Each call must return 422
    and leave the application's history empty.
    """
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


def test_malformed_json_is_rejected(api_client: TestClient) -> None:
    """Check that an incomplete JSON body returns 422 and creates no request."""
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
    api_client: TestClient, user_id: str | None, expected: int
) -> None:
    """Check that every mortgage endpoint requires a valid local user ID.

    A missing, malformed or non-positive header must return 422. A numeric
    ID that is not in the database must return 403. None of these calls may
    create a request.
    """
    headers = {"Idempotency-Key": "key"}
    if user_id is not None:
        headers["X-User-Id"] = user_id
    calls: list[tuple[str, str, dict[str, object] | None]] = [
        (
            "POST",
            "/requests",
            {"application_id": 1, "discount_bps": 25, "reason": "Offer"},
        ),
        ("GET", "/requests/1", None),
        ("POST", "/requests/1/decision", {"outcome": "APPROVED"}),
        ("GET", "/applications/1/requests", None),
        ("GET", "/applications/1/approved-discount", None),
    ]
    # The same identity rules apply to reads, submissions and decisions. (FR-03)
    for method, path, body in calls:
        response = api_client.request(method, path, headers=headers, json=body)
        assert response.status_code == expected
    assert history(api_client) == []


def test_roles_cannot_submit_or_decide_for_each_other(api_client: TestClient) -> None:
    """Check that managers and reviewers cannot perform each other's actions.

    A reviewer cannot submit, and a manager cannot approve. Expect 403 and
    leave the submitted request unchanged. A manager's decision must still
    return 403 when its request ID does not exist.
    """
    assert submit(api_client, user_id=3).status_code == 403
    original = submit(api_client).json()
    assert decide(api_client, original["id"], "APPROVED", user_id=1).status_code == 403
    assert history(api_client) == [original]
    assert decide(api_client, 999, "APPROVED", user_id=1).status_code == 403


def test_unknown_records_are_distinct_from_empty_history_and_no_approval(
    api_client: TestClient,
) -> None:
    """Distinguish an empty application from a record that does not exist.

    An application with no requests returns an empty history and no approval.
    Unknown request or application IDs return 404, including decisions and
    submissions. A corrected submission can reuse the rejected call's key.
    """
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
def test_decision_records_reviewer_and_time_and_cannot_be_replaced(
    api_client: TestClient, outcome: str
) -> None:
    """Check approval and decline, recorded decision details and later reads.

    Approve or decline a pending request. The response must retain the
    submitted fields and record the reviewer and a time within the call.
    Further decisions return 409 and leave history unchanged. Reading the
    request must return the saved decision. The approved discount lookup must
    return 25 basis points after approval, or None after decline.
    """
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
    # Neither repeating nor reversing a saved decision may replace it. (FR-08)
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
def test_invalid_decision_does_not_change_request(
    api_client: TestClient, body: dict[str, object]
) -> None:
    """Check that invalid decision fields leave the request unchanged.

    Reject missing or unsupported outcomes and attempts to supply a discount
    or reviewer in the body. Expect 422 and the original request in history.
    """
    original = submit(api_client).json()
    response = api_client.post(
        f"/requests/{original['id']}/decision", headers={"X-User-Id": "3"}, json=body
    )
    assert response.status_code == 422
    assert history(api_client) == [original]


@pytest.mark.parametrize("outcome", [None, "APPROVED", "DECLINED"])
def test_submitted_requests_cannot_be_edited_or_deleted(
    api_client: TestClient, outcome: str | None
) -> None:
    """Check that the API rejects edits and deletions of submitted requests.

    For pending, approved and declined requests, PUT, PATCH and DELETE must
    return 405. Reading history must show the original record unchanged.
    """
    original = submit(api_client).json()
    if outcome is not None:
        original = decide(api_client, original["id"], outcome).json()
    # Changing a submitted discount requires a new request. (FR-04)
    for method in ("PUT", "PATCH", "DELETE"):
        response = api_client.request(
            method,
            f"/requests/{original['id']}",
            headers={"X-User-Id": "1"},
            json={"discount_bps": 40},
        )
        assert response.status_code == 405
    assert history(api_client) == [original]


def test_changed_request_needs_decline_then_new_submission(
    api_client: TestClient,
) -> None:
    """Check that declining a pending request allows a changed submission.

    A second manager is blocked while the first request is pending. After
    the decline, the same rejected key can create a new pending request with
    a different ID. History must contain both the decline and the new request.
    """
    first = submit(api_client).json()
    # The pending-request limit covers all managers for this application. (FR-05)
    assert submit(api_client, key="second", user_id=2).status_code == 409
    declined = decide(api_client, first["id"], "DECLINED").json()
    response = submit(api_client, key="second", user_id=2, discount_bps=40)
    assert response.status_code == 201
    second = response.json()
    assert second["id"] != first["id"]
    assert second["status"] == "PENDING"
    assert history(api_client) == [declined, second]


def test_replacement_preserves_previous_approval_until_new_approval(
    api_client: TestClient,
) -> None:
    """Check when a replacement request changes the current approved discount.

    Start with an approval for 25 basis points. Submitting and then declining
    a request for 40 must leave 25 current. A later approval for 40 must become
    current, with all three requests and their decisions in history.
    """
    first = submit(api_client).json()
    approved = decide(api_client, first["id"], "APPROVED").json()
    first_approval = {"request_id": first["id"], "discount_bps": 25}
    second = submit(api_client, key="second", discount_bps=40).json()
    assert approval(api_client) == first_approval
    declined = decide(api_client, second["id"], "DECLINED").json()
    assert approval(api_client) == first_approval
    third = submit(api_client, key="third", discount_bps=40).json()
    # A later approval replaces the current discount and keeps earlier decisions.
    # History must retain all three requests. (FR-11, FR-12)
    replacement = decide(api_client, third["id"], "APPROVED").json()
    assert approval(api_client) == {"request_id": third["id"], "discount_bps": 40}
    assert history(api_client) == [approved, declined, replacement]


def test_history_and_approval_only_include_the_requested_application(
    api_client: TestClient,
) -> None:
    """Check that one application's records never appear in another's lookups.

    Approve 25 basis points for application 1. Application 2 must still have
    empty history and no approved discount. Then approve 60 for application 2.
    Each application must return only its own request, decision and discount.
    """
    # Both requests come from the same manager. Each lookup must still return
    # only the selected application's records. (FR-11, FR-12)
    first = submit(api_client, application_id=1, discount_bps=25)
    assert first.status_code == 201
    first_decision = decide(api_client, first.json()["id"], "APPROVED")
    assert first_decision.status_code == 200
    first_approved = first_decision.json()

    assert history(api_client, application_id=2) == []
    assert approval(api_client, application_id=2) is None

    second = submit(api_client, key="second", application_id=2, discount_bps=60)
    assert second.status_code == 201
    second_decision = decide(api_client, second.json()["id"], "APPROVED")
    assert second_decision.status_code == 200
    second_approved = second_decision.json()

    assert history(api_client, application_id=1) == [first_approved]
    assert history(api_client, application_id=2) == [second_approved]
    assert approval(api_client, application_id=1) == {
        "request_id": first_approved["id"],
        "discount_bps": 25,
    }
    assert approval(api_client, application_id=2) == {
        "request_id": second_approved["id"],
        "discount_bps": 60,
    }


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
def test_matching_retry_returns_current_state_even_when_later_request_is_pending(
    api_client: TestClient, outcome: str
) -> None:
    """Check that matching submissions return the same request's current state.

    Repeat a submission while it is pending, then again after approval or
    decline while a newer request is pending. Both retries must return 200
    with the original request ID and its stored state. History must still
    contain only the original request and the newer one.
    """
    first = submit(api_client).json()
    pending_retry = submit(api_client)
    assert pending_retry.status_code == 200
    assert pending_retry.json() == first
    decided = decide(api_client, first["id"], outcome).json()
    second = submit(api_client, key="second").json()
    # A newer pending request must not block a retry of an earlier one. (FR-14)
    repeated = submit(api_client)
    assert repeated.status_code == 200
    assert repeated.json() == decided
    assert history(api_client) == [decided, second]


@pytest.mark.parametrize(
    "changes",
    [{"application_id": 2}, {"discount_bps": 40}, {"reason": "Different offer"}],
)
def test_same_key_with_different_details_conflicts_before_and_after_decision(
    api_client: TestClient, changes: SubmissionChanges
) -> None:
    """Check that a saved submission key cannot be used with changed details.

    Change the application, discount or reason in separate cases. Reusing
    the original key must return 409 both while pending and after approval.
    History must still contain only the original request and its approval.
    """
    first = submit(api_client).json()
    assert submit(api_client, **changes).status_code == 409
    decided = decide(api_client, first["id"], "APPROVED").json()
    # Approval does not allow the key to be reused with different details. (FR-15)
    assert submit(api_client, **changes).status_code == 409
    assert history(api_client) == [decided]


def test_retry_key_is_scoped_to_user_and_reason_is_compared_exactly(
    api_client: TestClient,
) -> None:
    """Check that keys belong to users and that reason text is compared exactly.

    Changing only spaces or letter case must return 409 for the same user's
    key. Sending the original text again returns the same request. A different
    user can use the same key for another application and receive a new ID.
    """
    first = submit(api_client, reason=" Offer ").json()
    assert first["reason"] == " Offer "
    assert submit(api_client, reason="Offer").status_code == 409
    assert submit(api_client, reason=" offer ").status_code == 409
    assert submit(api_client, reason=" Offer ").json() == first
    second = submit(api_client, user_id=2, application_id=2)
    assert second.status_code == 201
    assert second.json()["id"] != first["id"]


def test_restart_preserves_decision_history_and_retry_mapping(
    api_database: Path,
) -> None:
    """Check that saved data survives closing and recreating the API app.

    Save an approval and a later pending request, then open a fresh app using
    the same SQLite file. History, current approval and a matching submission
    retry must return the previously saved values.
    """
    with TestClient(create_app(api_database)) as client:
        first = submit(client).json()
        decided = decide(client, first["id"], "APPROVED").json()
        second = submit(client, key="second").json()
    # The new app must read the existing file without recreating its data. (QR-01)
    with TestClient(create_app(api_database)) as client:
        assert history(client) == [decided, second]
        assert approval(client) == {"request_id": first["id"], "discount_bps": 25}
        repeated = submit(client)
        assert repeated.status_code == 200
        assert repeated.json() == decided


def test_initialisation_can_repeat_without_resetting_requests(
    api_client: TestClient, api_database: Path
) -> None:
    """Check that rerunning database setup preserves an existing request.

    Create a pending request, run create_database again on the same file,
    and confirm that history still contains the unchanged record.
    """
    original = submit(api_client).json()
    create_database(api_database)
    assert history(api_client) == [original]


def test_public_docs_describe_inputs_outputs_and_errors(api_client: TestClient) -> None:
    """Check public access and the generated API contract.

    Fetch health, Swagger UI and OpenAPI without identity headers. Check the
    route list, submission headers and response codes, required body fields,
    allowed decision outcomes and public request fields. The retry key stays
    out of the request response schema.
    """
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
        "X-User-Id",
        "Idempotency-Key",
    }
    models = schema["components"]["schemas"]
    assert set(models["Submission"]["required"]) == {
        "application_id",
        "discount_bps",
        "reason",
    }
    assert models["Submission"]["additionalProperties"] is False
    assert models["Decision"]["properties"]["outcome"]["enum"] == [
        "APPROVED",
        "DECLINED",
    ]
    assert set(models["RequestDetails"]["required"]) == {
        "id",
        "application_id",
        "discount_bps",
        "reason",
        "submitted_by",
        "submitted_at",
        "status",
        "reviewer_id",
        "decided_at",
    }
    assert "retry_key" not in models["RequestDetails"]["properties"]
