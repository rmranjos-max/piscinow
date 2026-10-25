import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MatchOverride(str, enum.Enum):
    NENHUM = "nenhum"
    INCLUIDA = "incluida"
    EXCLUIDA = "excluida"


class PartnerResponse(str, enum.Enum):
    PENDENTE = "pendente"
    EM_ANALISE = "em_analise"
    RECUSADA = "recusada"


class PartnerProfile(Base):
    """What a store serves. Maintained by the team only, during the pilot."""

    __tablename__ = "partner_profiles"
    __table_args__ = (CheckConstraint("capacity >= 1", name="ck_partner_profiles_capacity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), unique=True)
    service_areas: Mapped[list] = mapped_column(JSONB, default=list)
    pool_types: Mapped[list] = mapped_column(JSONB, default=list)
    budget_bands: Mapped[list] = mapped_column(JSONB, default=list)
    capacity: Mapped[int] = mapped_column(Integer, default=3)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)


class MatchingDecision(Base):
    """Why one store was, or was not, indicated for one deal, and what the store answered."""

    __tablename__ = "matching_decisions"
    __table_args__ = (UniqueConstraint("deal_id", "partner_member_id", name="uq_matching_decisions_deal_partner"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    partner_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    eligible: Mapped[bool] = mapped_column(Boolean)
    criteria: Mapped[list] = mapped_column(JSONB, default=list)
    override: Mapped[MatchOverride] = mapped_column(
        SAEnum(MatchOverride, name="match_override"), default=MatchOverride.NENHUM
    )
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    override_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response: Mapped[PartnerResponse] = mapped_column(
        SAEnum(PartnerResponse, name="partner_response"), default=PartnerResponse.PENDENTE
    )
    response_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
