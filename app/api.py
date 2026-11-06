from fastapi import APIRouter, Depends, Header, Path, Request, Response

from app import operations
from app.schemas import (
    SQLITE_MAX_INTEGER,
    ApplicationHistory,
    CurrentApproval,
    Decision,
    ErrorResponse,
    RequestDetails,
    Submission,
)


router = APIRouter(
    responses={
        403: {"model": ErrorResponse, "description": "Unknown user or disallowed role"},
        404: {"model": ErrorResponse, "description": "Record not found"},
        503: {"model": ErrorResponse, "description": "Database remains busy"},
    }
)


def get_session_factory(request: Request):
    """Return the session factory stored on the application at startup."""
    return request.app.state.sessions


def get_user_id(
    user_id: int = Header(alias="X-User-Id", gt=0, le=SQLITE_MAX_INTEGER),
):
    """Read the trusted local identity; operations check access. (FR-03)"""
    return user_id


@router.post(
    "/requests",
    status_code=201,
    response_model=RequestDetails,
    summary="Submit a discount request for review",
    description=(
        "Relationship manager only. Submit an application ID, requested discount "
        "and reason. The request starts as PENDING."
    ),
    responses={
        201: {"description": "Request created"},
        200: {"model": RequestDetails, "description": "Existing request returned"},
        409: {"model": ErrorResponse, "description": "Pending request or key conflict"},
    },
)
def submit(
    body: Submission,
    response: Response,
    retry_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        pattern=r"\S",
        description=(
            "Choose a new key for each submission. Reuse it with the same user "
            "and details to return the existing request's current state."
        ),
    ),
    user_id=Depends(get_user_id),
    sessions=Depends(get_session_factory),
):
    """Submit a discount request for review and return its details. (FR-01)"""
    request, status = operations.run_operation(
        sessions, operations.submit_request, user_id, retry_key, body
    )
    response.status_code = status
    return request


@router.get(
    "/requests/{request_id}",
    response_model=RequestDetails,
    summary="Read a request and its decision",
    description=(
        "Either role. Returns the submitted details, current status "
        "and decision if one has been recorded."
    ),
)
def read(
    request_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_session_factory),
):
    """Return the request's submitted details, status and decision. (FR-10)"""
    return operations.run_operation(
        sessions, operations.read_request, user_id, request_id
    )


@router.post(
    "/requests/{request_id}/decision",
    response_model=RequestDetails,
    summary="Approve or decline a pending request",
    description=(
        "Reviewer only. Records the outcome, reviewer and decision time "
        "for a pending request. Returns 409 if the request has already been decided."
    ),
    responses={409: {"model": ErrorResponse, "description": "Request already decided"}},
)
def decide(
    body: Decision,
    request_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_session_factory),
):
    """Approve or decline a pending request and return its details. (FR-06, FR-07)"""
    return operations.run_operation(
        sessions, operations.decide_request, user_id, request_id, body.outcome
    )


@router.get(
    "/applications/{application_id}/requests",
    response_model=ApplicationHistory,
    summary="Read all requests and decisions for an application",
    description=(
        "Either role. Returns all requests and their decisions for the application, "
        "ordered by request ID."
    ),
)
def history(
    application_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_session_factory),
):
    """Return all requests and decisions for a mortgage application. (FR-11)"""
    return operations.run_operation(
        sessions, operations.read_history, user_id, application_id
    )


@router.get(
    "/applications/{application_id}/approved-discount",
    response_model=CurrentApproval,
    summary="Read the current approved discount",
    description=(
        "Either role. Returns the current approved discount and its request ID. "
        "The approved_discount field is null if the application has no approval."
    ),
)
def approval(
    application_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_session_factory),
):
    """Return the application's current approved discount, if any. (FR-12)"""
    return operations.run_operation(
        sessions, operations.read_approval, user_id, application_id
    )
