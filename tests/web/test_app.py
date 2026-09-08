def test_app_serves_home_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Piscinow" in response.text
