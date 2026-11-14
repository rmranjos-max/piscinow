import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AssignmentStatus(str, enum.Enum):
    PENDENTE = "pendente"
    ACEITA = "aceita"
    RECUSADA = "recusada"
    CANCELADA = "cancelada"


class InstallerProfile(Base):
    """Where and what an installer serves. Maintained by the team only, as a hint for assigning."""

    __tablename__ = "installer_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), unique=True)
    service_areas: Mapped[list] = mapped_column(JSONB, default=list)
    service_kinds: Mapped[list] = mapped_column(JSONB, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class InstallerAssignment(Base):
    """The installer the team assigned to an accepted deal, and what the installer answered."""

    __tablename__ = "installer_assignments"
    __table_args__ = (
        # A deal has at most one live assignment; cancelled and declined ones are history.
        Index(
            "uq_installer_assignments_one_live_per_deal", "deal_id", unique=True,
            postgresql_where=text("status IN ('PENDENTE', 'ACEITA')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    installer_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    status: Mapped[AssignmentStatus] = mapped_column(
        SAEnum(AssignmentStatus, name="assignment_status"), default=AssignmentStatus.PENDENTE
    )
    assigned_reason: Mapped[str] = mapped_column(Text)
    assigned_by: Mapped[str] = mapped_column(String(200))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    response_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
