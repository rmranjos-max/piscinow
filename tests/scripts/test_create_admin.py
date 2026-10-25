from sqlalchemy import select

from piscinow.models.admin import AdminUser
from piscinow.scripts.create_admin import upsert_admin


def test_upsert_admin_creates_a_new_admin(db_session):
    created = upsert_admin(db_session, "novo@piscinow.com.br", "senha-forte-123")

    admin = db_session.scalar(select(AdminUser).where(AdminUser.email == "novo@piscinow.com.br"))
    assert created is True
    assert admin.verify_password("senha-forte-123") is True


def test_upsert_admin_resets_the_password_of_an_existing_admin(db_session):
    upsert_admin(db_session, "equipe@piscinow.com.br", "senha-antiga-123")

    created = upsert_admin(db_session, "equipe@piscinow.com.br", "senha-nova-456")

    admins = list(db_session.scalars(select(AdminUser).where(AdminUser.email == "equipe@piscinow.com.br")))
    assert created is False
    assert len(admins) == 1
    assert admins[0].verify_password("senha-nova-456") is True
    assert admins[0].verify_password("senha-antiga-123") is False
