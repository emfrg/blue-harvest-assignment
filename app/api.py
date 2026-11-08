from typing import cast

from fastapi import APIRouter, Depends, Header, Path, Request, Response
from sqlalchemy.orm import Session, sessionmaker

from app import operations
from app.schemas import (
    SQLITE_MAX_INTEGER,
    ApplicationHistory,
    CurrentApproval,
    Decision,
    DemoUser,
    ErrorResponse,
    RequestDetails,
    Submission,
)

# Add these shared error responses to the API documentation.
# The checks that trigger these errors are in operations.py.
router = APIRouter(
    responses={
        403: {"model": ErrorResponse, "description": "Unknown user or disallowed role"},
        404: {"model": ErrorResponse, "description": "Record not found"},
        503: {"model": ErrorResponse, "description": "Database remains busy"},
    }
)

demo_router = APIRouter(
    prefix="/demo",
    tags=["Frontend demo"],
    responses={503: {"model": ErrorResponse, "description": "Database remains busy"}},
)


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return the session factory stored on the application at startup."""
    return cast(sessionmaker[Session], request.app.state.sessions)


def get_user_id(
    user_id: int = Header(alias="X-User-Id", gt=0, le=SQLITE_MAX_INTEGER),
) -> int:
    """Return the user ID supplied in the X-User-Id header."""
    return user_id


@demo_router.get(
    "/users",
    response_model=list[DemoUser],
    summary="List demo users",
    description="Public. Returns stored user IDs and roles for the frontend demo.",
)
def demo_users(
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> list[DemoUser]:
    """Return the available users for the frontend demo."""
    return operations.run_operation(sessions, operations.list_demo_users)


@demo_router.get(
    "/applications",
    response_model=list[int],
    summary="List demo applications",
    description="Either role. Returns stored application IDs for the frontend demo.",
    responses={403: {"model": ErrorResponse, "description": "Unknown local user"}},
)
def demo_applications(
    user_id: int = Depends(get_user_id),
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> list[int]:
    """Return the available mortgage application IDs for the frontend demo."""
    return operations.run_operation(
        sessions, operations.list_demo_applications, user_id
    )


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
    user_id: int = Depends(get_user_id),
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> RequestDetails:
    """Submit a discount request for review and return its details."""
    request, status = operations.run_operation(
        sessions, operations.submit_request, user_id, retry_key, body
    )
    # Use 201 for a new request and 200 for an existing one.
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
    user_id: int = Depends(get_user_id),
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> RequestDetails:
    """Return the request's submitted details, status and decision."""
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
    user_id: int = Depends(get_user_id),
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> RequestDetails:
    """Approve or decline a pending request and return its details."""
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
    user_id: int = Depends(get_user_id),
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> ApplicationHistory:
    """Return all requests and decisions for a mortgage application."""
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
    user_id: int = Depends(get_user_id),
    sessions: sessionmaker[Session] = Depends(get_session_factory),
) -> CurrentApproval:
    """Return the application's current approved discount, if any."""
    return operations.run_operation(
        sessions, operations.read_approval, user_id, application_id
    )
