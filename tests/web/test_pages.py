from piscinow.models.member import Member, ProfileType


def test_convite_sets_cookie_for_valid_code(client, db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    response = client.get("/convite/RM7X2K9A", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.cookies.get("piscinow_ref") == "RM7X2K9A"


def test_convite_with_unknown_code_does_not_set_cookie(client):
    response = client.get("/convite/UNKNOWN1", follow_redirects=False)
    assert response.cookies.get("piscinow_ref") is None


def test_home_shows_referrer_name_when_cookie_present(client, db_session):
    referrer = Member(profile_type=ProfileType.EMBAIXADOR, name="Rodrigo Anjos", referral_code="RM7X2K9A")
    db_session.add(referrer)
    db_session.flush()

    client.cookies.set("piscinow_ref", "RM7X2K9A")
    response = client.get("/")

    assert "Rodrigo Anjos" in response.text
