import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from piscinow.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class QualificationStatus(str, enum.Enum):
    EM_ANDAMENTO = "em_andamento"
    QUALIFICADA = "qualificada"


class ConsentState(str, enum.Enum):
    NAO_RESPONDIDO = "nao_respondido"
    CONCEDIDO = "concedido"
    RECUSADO = "recusado"


class FieldSource(str, enum.Enum):
    CLIENTE = "cliente"
    PARCEIRO = "parceiro"
    ADMIN = "admin"


class Verification(str, enum.Enum):
    DECLARADO = "declarado"
    VERIFICADO = "verificado"
    PENDENTE = "pendente"


class DealStatus(str, enum.Enum):
    # The full lifecycle is declared now so later stages never need an enum migration.
    NEW = "new"
    QUALIFIED = "qualified"
    MATCHED = "matched"
    PARTNER_REVIEW = "partner_review"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    LOST = "lost"
    CANCELLED = "cancelled"


class LeadQualification(Base):
    __tablename__ = "lead_qualifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"), unique=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True
    )
    status: Mapped[QualificationStatus] = mapped_column(
        SAEnum(QualificationStatus, name="qualification_status"), default=QualificationStatus.EM_ANDAMENTO
    )
    consent: Mapped[ConsentState] = mapped_column(
        SAEnum(ConsentState, name="consent_state"), default=ConsentState.NAO_RESPONDIDO
    )
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    asks: Mapped[dict] = mapped_column(JSONB, default=dict)
    attention_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    attention_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    fields: Mapped[list["QualificationField"]] = relationship(
        back_populates="qualification", order_by="QualificationField.updated_at"
    )

    def values(self) -> dict:
        return {field.key: field.value for field in self.fields}


class QualificationField(Base):
    __tablename__ = "qualification_fields"
    __table_args__ = (UniqueConstraint("qualification_id", "key", name="uq_qualification_fields_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    qualification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lead_qualifications.id"))
    key: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(300))
    source: Mapped[FieldSource] = mapped_column(SAEnum(FieldSource, name="field_source"), default=FieldSource.CLIENTE)
    verification: Mapped[Verification] = mapped_column(
        SAEnum(Verification, name="verification_status"), default=Verification.DECLARADO
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    updated_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    qualification: Mapped["LeadQualification"] = relationship(back_populates="fields")


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        # A buyer has at most one active deal; closed ones (lost, cancelled) do not count.
        Index(
            "uq_deals_one_active_per_member",
            "member_id",
            unique=True,
            postgresql_where=text("status NOT IN ('LOST', 'CANCELLED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(Integer, Identity(start=1), unique=True)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("members.id"))
    qualification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lead_qualifications.id"))
    status: Mapped[DealStatus] = mapped_column(SAEnum(DealStatus, name="deal_status"), default=DealStatus.QUALIFIED)
    assigned_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    @property
    def code(self) -> str:
        return f"OP-{self.number:04d}"


class DealEvent(Base):
    __tablename__ = "deal_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("deals.id"))
    kind: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
