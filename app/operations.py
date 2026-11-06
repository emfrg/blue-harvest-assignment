from time import sleep

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models import DiscountRequest, MortgageApplication, User, current_utc_time


def run_operation(sessions, operation, *args):
    """Run an operation in a transaction, retrying known conflicts. (QR-02)"""
    for attempt in range(3):
        try:
            # Save all changes together when the block succeeds.
            # Roll them back if an error occurs. (QR-02)
            with sessions.begin() as session:
                result = operation(session, *args)
            return result
        except IntegrityError as error:
            message = str(error.orig)
            known_conflict = message in (
                "UNIQUE constraint failed: requests.submitted_by, requests.retry_key",
                "UNIQUE constraint failed: requests.application_id",
            )
            if not known_conflict or attempt == 2:
                raise
            # Another submission may have saved a request while this one was running.
            # A new transaction lets the operation check the latest saved data. (QR-02)
        except OperationalError as error:
            error_name = getattr(error.orig, "sqlite_errorname", "")
            if not error_name.startswith("SQLITE_BUSY"):
                raise
            if attempt == 2:
                raise HTTPException(503, "Database busy; try again") from error
            sleep(0.05 * (attempt + 1))


def check_user(session, user_id, required_role=None):
    """Reject unknown users or users without the required role. (FR-03)"""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(403, "Unknown local user")
    if required_role is not None and user.role != required_role:
        raise HTTPException(403, "Role not permitted")


def check_application(session, application_id):
    """Check that the application exists, or raise HTTP 404 if it is missing. (FR-13)"""
    if session.get(MortgageApplication, application_id) is None:
        raise HTTPException(404, "Application not found")


def find_request(session, request_id):
    """Return the stored request, or raise HTTP 404 if it is missing. (FR-13)"""
    request = session.get(DiscountRequest, request_id)
    if request is None:
        raise HTTPException(404, "Request not found")
    return request


def request_details(request):
    """Build the API response fields from a stored discount request. (FR-10)"""
    return {
        "id": request.id,
        "application_id": request.application_id,
        "discount_bps": request.discount_bps,
        "reason": request.reason,
        "submitted_by": request.submitted_by,
        "submitted_at": request.submitted_at,
        "status": request.status,
        "reviewer_id": request.reviewer_id,
        "decided_at": request.decided_at,
    }


def submit_request(session, user_id, retry_key, submission):
    """Submit a new request or retrieve the original on retry. (FR-01, FR-14)"""
    check_user(session, user_id, "RELATIONSHIP_MANAGER")
    # Check for a previous submission first so a retry can return it,
    # even when that request is still pending. (FR-14)
    original = session.scalar(
        select(DiscountRequest).where(
            DiscountRequest.submitted_by == user_id,
            DiscountRequest.retry_key == retry_key,
        )
    )
    if original is not None:
        if (
            original.application_id != submission.application_id
            or original.discount_bps != submission.discount_bps
            or original.reason != submission.reason
        ):
            raise HTTPException(409, "Retry key already used with different details")
        return request_details(original), 200

    # A new submission needs an existing application with no pending request.
    check_application(session, submission.application_id)
    pending = session.scalar(
        select(DiscountRequest.id).where(
            DiscountRequest.application_id == submission.application_id,
            DiscountRequest.status == "PENDING",
        )
    )
    if pending is not None:
        raise HTTPException(409, "Application already has a pending request")

    request = DiscountRequest(
        application_id=submission.application_id,
        discount_bps=submission.discount_bps,
        reason=submission.reason,
        submitted_by=user_id,
        retry_key=retry_key,
    )
    session.add(request)
    # Flush inserts the request and fills in its ID, submission time and status.
    # run_operation commits the transaction when the operation succeeds. (FR-01)
    session.flush()
    return request_details(request), 201


def read_request(session, user_id, request_id):
    """Return request details after checking the user's access. (FR-03, FR-10)"""
    check_user(session, user_id)
    return request_details(find_request(session, request_id))


def decide_request(session, user_id, request_id, outcome):
    """Record one final decision with its reviewer and time. (FR-08, FR-09)"""
    check_user(session, user_id, "REVIEWER")
    # The database applies this update only if the request is still PENDING.
    # An existing approval or decline is left unchanged. (FR-08, QR-02)
    result = session.execute(
        update(DiscountRequest)
        .where(DiscountRequest.id == request_id, DiscountRequest.status == "PENDING")
        .values(status=outcome, reviewer_id=user_id, decided_at=current_utc_time())
    )
    # A missing request and an already decided request both produce zero updated rows.
    # This lookup raises 404 for a missing request. (FR-13)
    request = find_request(session, request_id)
    if result.rowcount == 0:
        raise HTTPException(409, "Request already decided")
    return request_details(request)


def read_history(session, user_id, application_id):
    """Return the application's requests and decisions, oldest first. (FR-11)"""
    check_user(session, user_id)
    check_application(session, application_id)
    requests = session.scalars(
        select(DiscountRequest)
        .where(DiscountRequest.application_id == application_id)
        .order_by(DiscountRequest.id)
    ).all()
    return {
        "application_id": application_id,
        "requests": [request_details(request) for request in requests],
    }


def read_approval(session, user_id, application_id):
    """Return the application ID and the current approved discount details.

    The approved_discount field is None when no request has been approved. (FR-12)
    """
    check_user(session, user_id)
    check_application(session, application_id)
    request = session.scalar(
        select(DiscountRequest)
        .where(
            DiscountRequest.application_id == application_id,
            DiscountRequest.status == "APPROVED",
        )
        .order_by(DiscountRequest.id.desc())
        .limit(1)
    )
    approval = None
    if request is not None:
        approval = {"request_id": request.id, "discount_bps": request.discount_bps}
    return {"application_id": application_id, "approved_discount": approval}
