from piscinow.models.admin import AdminUser


def test_login_with_correct_credentials_redirects_to_fila(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/admin/login",
        data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/fila"


def test_login_with_wrong_password_shows_error(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()

    response = client.post(
        "/admin/login", data={"email": "equipe@piscinow.com.br", "password": "errada"}
    )

    assert response.status_code == 401
    assert "invalidos" in response.text
