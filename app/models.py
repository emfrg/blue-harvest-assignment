from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def current_utc_time():
    """Return the current UTC date and time as text."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


class MortgageApplication(Base):
    __tablename__ = "mortgage_applications"

    id = Column(Integer, primary_key=True)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    role = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role IN ('RELATIONSHIP_MANAGER', 'REVIEWER')", name="valid_user_role"
        ),
    )


class DiscountRequest(Base):
    """A mortgage discount request with its status and any review decision."""

    __tablename__ = "requests"

    id = Column(Integer, primary_key=True)
    application_id = Column(
        Integer, ForeignKey("mortgage_applications.id"), nullable=False
    )
    discount_bps = Column(Integer, nullable=False)
    reason = Column(Text, nullable=False)
    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    submitted_at = Column(Text, nullable=False, default=current_utc_time)
    status = Column(Text, nullable=False, default="PENDING")
    retry_key = Column(Text, nullable=False)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(Text, nullable=True)

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
