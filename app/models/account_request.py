import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Uuid, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPKMixin


class AccountRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class TenantAccountRequest(UUIDPKMixin, Base):
    """A public visitor's request for a new tenant account — predates any
    Organization, so it carries no organization_id. Approval provisions a
    real Organization (see services/platform.py::provision_organization)
    and links it here via organization_id."""

    __tablename__ = "tenant_account_requests"

    organization_name: Mapped[str] = mapped_column(String(200), nullable=False)
    applicant_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    expected_usage: Mapped[str | None] = mapped_column(String(500), nullable=True)
    additional_info: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    status: Mapped[AccountRequestStatus] = mapped_column(
        Enum(AccountRequestStatus, name="account_request_status"), default=AccountRequestStatus.PENDING, nullable=False
    )
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
