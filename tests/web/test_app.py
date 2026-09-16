def test_app_serves_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Piscinow" in response.text


def test_app_serves_loja_login_page(client):
    response = client.get("/loja/login")
    assert response.status_code == 200
    assert "Painel da loja" in response.text
