def test_app_serves_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Piscinow" in response.text


def test_app_serves_loja_login_page(client):
    response = client.get("/loja/login")
    assert response.status_code == 200
    assert "Painel da loja" in response.text


def test_app_serves_prestador_login_page(client):
    response = client.get("/prestador/login")
    assert response.status_code == 200
    assert "Painel do prestador" in response.text


def test_app_serves_vitrine_produtos_page(client):
    response = client.get("/vitrine/produtos")
    assert response.status_code == 200


def test_app_serves_comprador_login_page(client):
    response = client.get("/comprador/login")
    assert response.status_code == 200
    assert "Painel do comprador" in response.text
