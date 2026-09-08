import sys

from piscinow.db import make_engine, make_session_factory
from piscinow.models.admin import AdminUser


def main() -> None:
    if len(sys.argv) != 3:
        print("uso: python -m piscinow.scripts.create_admin <email> <senha>")
        raise SystemExit(1)
    email, password = sys.argv[1], sys.argv[2]
    engine = make_engine()
    session = make_session_factory(engine)()
    session.add(AdminUser.create(email=email, password=password))
    session.commit()
    print(f"admin criado: {email}")


if __name__ == "__main__":
    main()
