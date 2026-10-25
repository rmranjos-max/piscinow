import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.db import make_engine, make_session_factory
from piscinow.models.admin import AdminUser


def upsert_admin(session: Session, email: str, password: str) -> bool:
    """Creates the admin, or resets the password if the email already exists. True when created."""
    existing = session.scalar(select(AdminUser).where(AdminUser.email == email))
    if existing is not None:
        existing.set_password(password)
        session.flush()
        return False
    session.add(AdminUser.create(email=email, password=password))
    session.flush()
    return True


def main() -> None:
    if len(sys.argv) != 3:
        print("uso: python -m piscinow.scripts.create_admin <email> <senha>")
        raise SystemExit(1)
    email, password = sys.argv[1], sys.argv[2]
    engine = make_engine()
    session = make_session_factory(engine)()
    created = upsert_admin(session, email, password)
    session.commit()
    print(f"admin criado: {email}" if created else f"senha do admin atualizada: {email}")


if __name__ == "__main__":
    main()
