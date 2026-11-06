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


def get_sessions(request: Request):
    return request.app.state.sessions


def get_user_id(
    user_id: int = Header(alias="X-User-Id", gt=0, le=SQLITE_MAX_INTEGER),
):
    return user_id


@router.post(
    "/requests",
    status_code=201,
    response_model=RequestDetails,
    summary="Submit a discount request",
    description="Manager only. Matching retries return the original request's state.",
    responses={
        200: {"model": RequestDetails, "description": "Matching submission retry"},
        409: {"model": ErrorResponse, "description": "Pending request or key conflict"},
    },
)
def submit(
    body: Submission,
    response: Response,
    retry_key: str = Header(alias="Idempotency-Key", min_length=1, pattern=r"\S"),
    user_id=Depends(get_user_id),
    sessions=Depends(get_sessions),
):
    request, status = operations.run_operation(
        sessions, operations.submit_request, user_id, retry_key, body
    )
    response.status_code = status
    return request


@router.get(
    "/requests/{request_id}",
    response_model=RequestDetails,
    summary="Read a request and its decision",
)
def read(
    request_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_sessions),
):
    return operations.run_operation(
        sessions, operations.read_request, user_id, request_id
    )


@router.post(
    "/requests/{request_id}/decision",
    response_model=RequestDetails,
    summary="Approve or decline a pending request",
    description=(
        "Reviewer only. Final decisions cannot change. "
        "The submitted discount stays fixed."
    ),
    responses={409: {"model": ErrorResponse, "description": "Request already decided"}},
)
def decide(
    body: Decision,
    request_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_sessions),
):
    return operations.run_operation(
        sessions, operations.decide_request, user_id, request_id, body.outcome
    )


@router.get(
    "/applications/{application_id}/requests",
    response_model=ApplicationHistory,
    summary="Read all requests and decisions for an application",
    description="Either role. All requests remain available, ordered by request ID.",
)
def history(
    application_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_sessions),
):
    return operations.run_operation(
        sessions, operations.read_history, user_id, application_id
    )


@router.get(
    "/applications/{application_id}/approved-discount",
    response_model=CurrentApproval,
    summary="Read the current approved discount",
    description="Either role. An existing application without approval returns null.",
)
def approval(
    application_id: int = Path(gt=0, le=SQLITE_MAX_INTEGER),
    user_id=Depends(get_user_id),
    sessions=Depends(get_sessions),
):
    return operations.run_operation(
        sessions, operations.read_approval, user_id, application_id
    )
