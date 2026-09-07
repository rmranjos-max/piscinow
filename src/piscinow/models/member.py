import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base


class ProfileType(str, enum.Enum):
    COMPRADOR = "comprador"
    LOJA = "loja"
    PRESTADOR = "prestador"
    EMBAIXADOR = "embaixador"


class MemberStatus(str, enum.Enum):
    PENDING = "pending"        # conversa em andamento, dados incompletos
    WAITLISTED = "waitlisted"  # dados completos, aguardando revisao manual
    APPROVED = "approved"      # admitido no Clube / homologado
    REJECTED = "rejected"      # recusado pela equipe


class Member(Base):
    __tablename__ = "members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_type: Mapped[ProfileType] = mapped_column(SAEnum(ProfileType, name="profile_type"))
    status: Mapped[MemberStatus] = mapped_column(
        SAEnum(MemberStatus, name="member_status"), default=MemberStatus.PENDING
    )
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    region: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_details: Mapped[dict] = mapped_column(JSONB, default=dict)
    referral_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    referred_by_member_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("members.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)

    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = uuid.uuid4()
        if 'status' not in kwargs:
            kwargs['status'] = MemberStatus.PENDING
        if 'profile_details' not in kwargs:
            kwargs['profile_details'] = {}
        if 'created_at' not in kwargs:
            kwargs['created_at'] = datetime.utcnow()
        super().__init__(**kwargs)

    def submit_for_review(self) -> None:
        if self.status != MemberStatus.PENDING:
            raise ValueError(f"cannot submit member in status {self.status}")
        self.status = MemberStatus.WAITLISTED

    def approve(self, *, approved_by: str) -> None:
        self.status = MemberStatus.APPROVED
        self.approved_by = approved_by
        self.approved_at = datetime.utcnow()

    def reject(self, *, approved_by: str) -> None:
        self.status = MemberStatus.REJECTED
        self.approved_by = approved_by
        self.approved_at = datetime.utcnow()

    def auto_approve_via_referral(self) -> None:
        if self.referred_by_member_id is None:
            raise ValueError("cannot auto-approve a member without a referral")
        self.status = MemberStatus.APPROVED
        self.approved_by = "referral"
        self.approved_at = datetime.utcnow()
