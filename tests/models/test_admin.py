from piscinow.models.admin import AdminUser


def test_create_hashes_the_password():
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    assert admin.password_hash != "senha-forte-123"


def test_verify_password_accepts_correct_password():
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    assert admin.verify_password("senha-forte-123") is True


def test_verify_password_rejects_wrong_password():
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    assert admin.verify_password("errada") is False
