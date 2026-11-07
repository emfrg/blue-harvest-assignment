from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SQLITE_MAX_INTEGER = 9223372036854775807


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Reject strings and booleans in integer fields. (FR-02)
    application_id: int = Field(strict=True, gt=0, le=SQLITE_MAX_INTEGER)
    discount_bps: int = Field(strict=True, gt=0, le=SQLITE_MAX_INTEGER)
    reason: str = Field(strict=True, min_length=1, pattern=r"\S")


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["APPROVED", "DECLINED"]


class RequestDetails(BaseModel):
    id: int
    application_id: int
    discount_bps: int
    reason: str
    submitted_by: int
    # Describe this string as a date and time in the API schema.
    submitted_at: str = Field(json_schema_extra={"format": "date-time"})
    status: Literal["PENDING", "APPROVED", "DECLINED"]
    reviewer_id: int | None
    decided_at: str | None = Field(json_schema_extra={"format": "date-time"})


class ApplicationHistory(BaseModel):
    application_id: int
    requests: list[RequestDetails]


class ApprovedDiscount(BaseModel):
    request_id: int
    discount_bps: int


class CurrentApproval(BaseModel):
    application_id: int
    approved_discount: ApprovedDiscount | None


class ErrorResponse(BaseModel):
    detail: str
