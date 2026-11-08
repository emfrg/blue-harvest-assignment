from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def current_utc_time() -> str:
    """Return the current UTC date and time as text."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


class MortgageApplication(Base):
    __tablename__ = "mortgage_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role IN ('RELATIONSHIP_MANAGER', 'REVIEWER')", name="valid_user_role"
        ),
    )


class DiscountRequest(Base):
    """A mortgage discount request with its status and any review decision."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mortgage_applications.id"), nullable=False
    )
    discount_bps: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    submitted_at: Mapped[str] = mapped_column(
        Text, nullable=False, default=current_utc_time
    )
    status: Mapped[Literal["PENDING", "APPROVED", "DECLINED"]] = mapped_column(
        Text, nullable=False, default="PENDING"
    )
    retry_key: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # SQLite integer columns can also store decimals; check the type. (FR-02)
        CheckConstraint(
            "typeof(discount_bps) = 'integer' AND discount_bps > 0",
            name="positive_whole_discount",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'DECLINED')", name="valid_request_status"
        ),
        # Pending requests have no reviewer or decision time.
        # Approved and declined requests must have both. (FR-09)
        CheckConstraint(
            "(status = 'PENDING' AND reviewer_id IS NULL AND decided_at IS NULL) OR "
            "(status IN ('APPROVED', 'DECLINED') "
            "AND reviewer_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="decision_matches_status",
        ),
        # A user's submission key stays linked to the original request,
        # including after the request is approved or declined. (FR-14)
        UniqueConstraint(
            "submitted_by", "retry_key", name="unique_submitter_retry_key"
        ),
        # This unique index allows at most one PENDING request per application.
        # An application can still have multiple approved or declined requests. (FR-05)
        Index(
            "one_pending_request_per_application",
            "application_id",
            unique=True,
            sqlite_where=text("status = 'PENDING'"),
        ),
    )
