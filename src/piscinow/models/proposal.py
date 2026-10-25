import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint, Date, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from piscinow.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProposalStatus(str, enum.Enum):
    ENVIADA = "enviada"
    SUBSTITUIDA = "substituida"
    RECUSADA = "recusada"
    ACEITA = "aceita"
    ENCERRADA = "encerrada"  # another store's proposal was accepted


class MessageAuthor(str, enum.Enum):
    COMPRADOR = "comprador"
    LOJA = "loja"


class FeasibilityStatus(str, enum.Enum):
    PENDING = "pending"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class Proposal(Base):
    """One immutable version of a store's offer for a deal."""

    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("deal_id", "partner_member_id", "version", name="uq_proposals_version"),
        Index(
            "uq_proposals_one_open_per_partner", "deal_id", "partner_member_id", unique=True,
            postgresql_where=text("status = 'ENVIADA'"),
        ),
        Index("uq_proposals_one_accepted_per_deal", "deal_id", unique=True, postgresql_where=text("status = 'ACEITA'")),
        CheckConstraint("total > 0", name="ck_proposals_total_positive"),
        CheckConstraint("lead_time_days > 0", name="ck_proposals_lead_time_positive"),
        CheckConstraint("version > 0", name="ck_proposals_version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    partner_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[ProposalStatus] = mapped_column(
        SAEnum(ProposalStatus, name="proposal_status"), default=ProposalStatus.ENVIADA
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    scope: Mapped[str] = mapped_column(Text)
    lead_time_days: Mapped[int] = mapped_column(Integer)
    valid_until: Mapped[date] = mapped_column(Date)
    exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str] = mapped_column(String(200))

    items: Mapped[list["ProposalItem"]] = relationship(order_by="ProposalItem.position")


class ProposalItem(Base):
    __tablename__ = "proposal_items"
    __table_args__ = (CheckConstraint("amount > 0", name="ck_proposal_items_amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("proposals.id"))
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class DealMessage(Base):
    """Negotiation thread between the buyer and one store, kept on the deal."""

    __tablename__ = "deal_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    partner_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    author: Mapped[MessageAuthor] = mapped_column(SAEnum(MessageAuthor, name="message_author"))
    author_member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    is_revision_request: Mapped[bool] = mapped_column(default=False)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class FeasibilityCheck(Base):
    __tablename__ = "feasibility_checks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"), unique=True)
    status: Mapped[FeasibilityStatus] = mapped_column(
        SAEnum(FeasibilityStatus, name="feasibility_status"), default=FeasibilityStatus.PENDING
    )
    items: Mapped[list] = mapped_column(JSONB, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
