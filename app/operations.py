from collections.abc import Callable
from time import sleep
from typing import Concatenate, Literal, ParamSpec, TypeVar, cast

from fastapi import HTTPException
from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.models import DiscountRequest, MortgageApplication, User, current_utc_time
from app.schemas import (
    ApplicationHistory,
    ApprovedDiscount,
    CurrentApproval,
    RequestDetails,
    Submission,
)

OperationArgs = ParamSpec("OperationArgs")
OperationResult = TypeVar("OperationResult")


def run_operation(
    sessions: sessionmaker[Session],
    operation: Callable[Concatenate[Session, OperationArgs], OperationResult],
    *args: OperationArgs.args,
    **kwargs: OperationArgs.kwargs,
) -> OperationResult:
    """Run an operation in a transaction, retrying known database conflicts.

    Make up to three attempts for SQLite busy errors or conflicts with the
    submission-key or single-pending-request uniqueness constraints.
    Other errors are raised immediately.
    """
    attempt = 0
    while True:
        try:
            # Save all changes together when the block succeeds.
            # Roll them back if an error occurs.
            with sessions.begin() as session:
                result = operation(session, *args, **kwargs)
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
        attempt += 1


def check_user(
    session: Session, user_id: int, required_role: str | None = None
) -> None:
    """Reject unknown users or users without the required role."""
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(403, "Unknown local user")
    if required_role is not None and user.role != required_role:
        raise HTTPException(403, "Role not permitted")


def check_application(session: Session, application_id: int) -> None:
    """Check that the application exists, or raise HTTP 404 if it is missing."""
    if session.get(MortgageApplication, application_id) is None:
        raise HTTPException(404, "Application not found")


def find_request(session: Session, request_id: int) -> DiscountRequest:
    """Return the stored request, or raise HTTP 404 if it is missing."""
    request = session.get(DiscountRequest, request_id)
    if request is None:
        raise HTTPException(404, "Request not found")
    return request


def request_details(request: DiscountRequest) -> RequestDetails:
    """Build the API response fields from a stored discount request."""
    return RequestDetails(
        id=request.id,
        application_id=request.application_id,
        discount_bps=request.discount_bps,
        reason=request.reason,
        submitted_by=request.submitted_by,
        submitted_at=request.submitted_at,
        status=request.status,
        reviewer_id=request.reviewer_id,
        decided_at=request.decided_at,
    )


def submit_request(
    session: Session, user_id: int, retry_key: str, submission: Submission
) -> tuple[RequestDetails, int]:
    """Submit a new request or retrieve the original on retry.

    Returns:
        A tuple of request details and HTTP status: 201 for a new request,
        or 200 for a matching retry.
    """
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
    # run_operation commits the transaction when the operation succeeds.
    session.flush()
    return request_details(request), 201


def read_request(session: Session, user_id: int, request_id: int) -> RequestDetails:
    """Return request details after checking the user's access."""
    check_user(session, user_id)
    return request_details(find_request(session, request_id))


def decide_request(
    session: Session,
    user_id: int,
    request_id: int,
    outcome: Literal["APPROVED", "DECLINED"],
) -> RequestDetails:
    """Record one final decision with its reviewer and time."""
    check_user(session, user_id, "REVIEWER")
    # The database applies this update only if the request is still PENDING.
    # An existing approval or decline is left unchanged. (FR-08, QR-02)
    result = cast(
        CursorResult[tuple[object, ...]],
        session.execute(
            update(DiscountRequest)
            .where(
                DiscountRequest.id == request_id, DiscountRequest.status == "PENDING"
            )
            .values(status=outcome, reviewer_id=user_id, decided_at=current_utc_time())
        ),
    )
    # A missing request and an already decided request both produce zero updated rows.
    # This lookup raises 404 for a missing request. (FR-13)
    request = find_request(session, request_id)
    if result.rowcount == 0:
        raise HTTPException(409, "Request already decided")
    return request_details(request)


def read_history(
    session: Session, user_id: int, application_id: int
) -> ApplicationHistory:
    """Return the application's requests and decisions, oldest first."""
    check_user(session, user_id)
    check_application(session, application_id)
    requests = session.scalars(
        select(DiscountRequest)
        .where(DiscountRequest.application_id == application_id)
        .order_by(DiscountRequest.id)
    ).all()
    return ApplicationHistory(
        application_id=application_id,
        requests=[request_details(request) for request in requests],
    )


def read_approval(
    session: Session, user_id: int, application_id: int
) -> CurrentApproval:
    """Return the application ID and the current approved discount details.

    Returns:
        A CurrentApproval response containing application_id and approved_discount.
        The approved_discount field contains the approved request's ID and
        discount, or None if the application has no approved requests.
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
        approval = ApprovedDiscount(
            request_id=request.id, discount_bps=request.discount_bps
        )
    return CurrentApproval(application_id=application_id, approved_discount=approval)
