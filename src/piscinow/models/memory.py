import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base
from piscinow.models.member import ProfileType

EMBEDDING_DIM = 384


class MemoryKind(str, enum.Enum):
    FACT = "fact"
    RULE = "rule"
    FAQ = "faq"
    CORRECTION = "correction"


class MemorySource(str, enum.Enum):
    AUTO = "auto"
    HUMAN = "human"


class MemoryItem(Base):
    __tablename__ = "memory_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[MemoryKind] = mapped_column(SAEnum(MemoryKind, name="memory_kind"))
    source: Mapped[MemorySource] = mapped_column(SAEnum(MemorySource, name="memory_source"))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    profile_type: Mapped[ProfileType | None] = mapped_column(
        SAEnum(ProfileType, name="profile_type"), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_items.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
