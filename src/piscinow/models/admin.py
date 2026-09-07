import uuid
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from piscinow.db import Base

_hasher = PasswordHasher()


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(200), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    @classmethod
    def create(cls, *, email: str, password: str) -> "AdminUser":
        return cls(email=email, password_hash=_hasher.hash(password))

    def verify_password(self, password: str) -> bool:
        try:
            return _hasher.verify(self.password_hash, password)
        except VerifyMismatchError:
            return False
