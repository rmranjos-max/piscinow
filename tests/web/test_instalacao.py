from piscinow.installation.service import assign_installer, get_installer_profile, respond_assignment, save_installer_profile
from piscinow.models.admin import AdminUser
from piscinow.models.installation import AssignmentStatus, InstallerAssignment
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.proposals.service import accept_proposal
from tests.proposals.test_service import _approve_feasibility, _loja, _send, _setup

ACTOR = "admin:equipe@piscinow.com.br"
BUYER_EMAIL, BUYER_PHONE = "marina@example.com", "(19) 99999-0000"


def _admin(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})


def _installer(db_session, name="Instalações Sul", email="inst@example.com", areas="Valinhos", profile=True):
    member = Member(profile_type=ProfileType.PRESTADOR, name=name, status=MemberStatus.APPROVED, email=email)
    member.set_password("senha-forte-123")
    db_session.add(member)
    db_session.flush()
    if profile:
        save_installer_profile(db_session, member, areas=areas, service_kinds=["instalacao"], active=True, actor=ACTOR)
    return member


def _accepted(db_session):
    loja = _loja(db_session)
    buyer, qualification, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    accept_proposal(db_session, _send(db_session, decisions[loja.id]), buyer)
    return buyer, qualification, deal


def _installer_login(client, email="inst@example.com"):
    client.post("/prestador/login", data={"email": email, "password": "senha-forte-123"})


def test_the_profile_form_requires_an_admin_and_only_exists_for_installers(client, db_session):
    installer = _installer(db_session, profile=False)
    assert client.get(f"/admin/prestadores/{installer.id}/atendimento", follow_redirects=False).status_code == 303

    _admin(client, db_session)
    store = Member(profile_type=ProfileType.LOJA, name="Loja", status=MemberStatus.APPROVED)
    db_session.add(store)
    db_session.flush()
    assert client.get(f"/admin/prestadores/{installer.id}/atendimento").status_code == 200
    assert client.get(f"/admin/prestadores/{store.id}/atendimento").status_code == 404
    assert client.get("/admin/prestadores/nao-uuid/atendimento").status_code == 404


def test_the_admin_saves_an_installer_profile(client, db_session):
    _admin(client, db_session)
    installer = _installer(db_session, profile=False)

    response = client.post(
        f"/admin/prestadores/{installer.id}/atendimento",
        data={"areas": "Valinhos, Vinhedo", "service_kinds": ["instalacao", "reparo"], "active": "on"}, follow_redirects=False,
    )

    assert response.status_code == 303
    profile = get_installer_profile(db_session, installer.id)
    assert (profile.service_areas, profile.service_kinds, profile.active) == (["Valinhos", "Vinhedo"], ["instalacao", "reparo"], True)
    assert profile.updated_by == ACTOR


def test_an_invalid_installer_profile_shows_the_error_and_saves_nothing(client, db_session):
    _admin(client, db_session)
    installer = _installer(db_session, profile=False)

    response = client.post(f"/admin/prestadores/{installer.id}/atendimento", data={"areas": "Valinhos"})

    assert response.status_code == 400
    assert "ao menos um tipo de serviço" in response.text
    assert get_installer_profile(db_session, installer.id) is None


def test_the_installers_list_links_to_each_profile(client, db_session):
    _admin(client, db_session)
    installer = _installer(db_session)

    assert f"/admin/prestadores/{installer.id}/atendimento" in client.get("/admin/prestadores").text


def test_the_installation_block_is_only_offered_for_an_accepted_opportunity(client, db_session):
    _admin(client, db_session)
    _installer(db_session)
    loja = _loja(db_session)
    _, qualification, deal, _ = _setup(db_session, loja)

    assert "Atribuir instalador" not in client.get(f"/admin/oportunidades/{qualification.id}").text
    assert client.post(f"/admin/oportunidades/{qualification.id}/instalador", data={"instalador": "x", "motivo": "x"}).status_code == 400


def test_the_admin_sees_the_candidates_with_the_city_hint_and_assigns_one(client, db_session):
    _admin(client, db_session)
    near = _installer(db_session, "Perto", "perto@example.com", areas="Valinhos")
    _installer(db_session, "Longe", "longe@example.com", areas="Sorocaba")
    _, qualification, deal = _accepted(db_session)

    page = client.get(f"/admin/oportunidades/{qualification.id}").text
    assert "Atribuir instalador" in page and "Atende Valinhos" in page and "Não atende Valinhos" in page

    response = client.post(
        f"/admin/oportunidades/{qualification.id}/instalador",
        data={"instalador": str(near.id), "motivo": "Atende a região"}, follow_redirects=True,
    )

    assert response.status_code == 200
    assignment = db_session.query(InstallerAssignment).one()
    assert (assignment.installer_member_id, assignment.status) == (near.id, AssignmentStatus.PENDENTE)
    assert assignment.assigned_by == ACTOR
    assert "Aguardando resposta" in response.text


def test_assigning_without_a_reason_or_with_an_unknown_installer_is_refused(client, db_session):
    _admin(client, db_session)
    installer = _installer(db_session)
    _, qualification, _ = _accepted(db_session)
    url = f"/admin/oportunidades/{qualification.id}/instalador"

    assert client.post(url, data={"instalador": str(installer.id), "motivo": " "}).status_code == 400
    assert client.post(url, data={"instalador": "nao-uuid", "motivo": "x"}).status_code == 400
    assert client.post(url, data={"instalador": "00000000-0000-0000-0000-000000000000", "motivo": "x"}).status_code == 400
    assert db_session.query(InstallerAssignment).count() == 0


def test_the_installer_inbox_requires_login_and_starts_empty(client, db_session):
    assert client.get("/prestador/instalacoes", follow_redirects=False).headers["location"] == "/prestador/login"
    _installer(db_session)
    _installer_login(client)

    assert "Nenhuma instalação" in client.get("/prestador/instalacoes").text


def test_the_installer_sees_the_project_without_price_or_contact_before_accepting(client, db_session):
    installer = _installer(db_session)
    buyer, _, deal = _accepted(db_session)
    assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    _installer_login(client)

    page = client.get("/prestador/instalacoes").text

    assert "Cliente #" in page and "Valinhos" in page and "Fornecimento e instalação" in page
    assert "Studio Fibra Sul" in page
    for hidden in ("Marina", BUYER_EMAIL, BUYER_PHONE, "21.000", "R$ 21"):
        assert hidden not in page


def test_accepting_releases_the_contact_to_that_installer_only(client, db_session):
    installer, other = _installer(db_session), _installer(db_session, "Outro", "outro@example.com")
    buyer, _, deal = _accepted(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    _installer_login(client)

    response = client.post(f"/prestador/instalacoes/{assignment.id}/resposta", data={"decisao": "aceita"}, follow_redirects=True)

    assert assignment.status == AssignmentStatus.ACEITA
    assert "Marina Duarte" in response.text and BUYER_PHONE in response.text
    client.post("/prestador/logout")
    _installer_login(client, "outro@example.com")
    theirs = client.get("/prestador/instalacoes").text
    assert "Marina" not in theirs and "Cliente #" not in theirs


def test_declining_needs_a_reason(client, db_session):
    installer = _installer(db_session)
    _, _, deal = _accepted(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    _installer_login(client)
    url = f"/prestador/instalacoes/{assignment.id}/resposta"

    assert client.post(url, data={"decisao": "recusada", "motivo": " "}).status_code == 400
    client.post(url, data={"decisao": "recusada", "motivo": "Agenda cheia"})

    assert (assignment.status, assignment.response_reason) == (AssignmentStatus.RECUSADA, "Agenda cheia")


def test_an_installer_cannot_answer_for_another_installer(client, db_session):
    mine, other = _installer(db_session), _installer(db_session, "Outro", "outro@example.com")
    _, _, deal = _accepted(db_session)
    assignment = assign_installer(db_session, deal, other, reason="Atende", actor=ACTOR)
    _installer_login(client)

    response = client.post(f"/prestador/instalacoes/{assignment.id}/resposta", data={"decisao": "aceita"})

    assert response.status_code == 404
    assert assignment.status == AssignmentStatus.PENDENTE


def test_a_cancelled_assignment_cannot_be_answered(client, db_session):
    first, second = _installer(db_session), _installer(db_session, "Outro", "outro@example.com")
    _, _, deal = _accepted(db_session)
    old = assign_installer(db_session, deal, first, reason="Atende", actor=ACTOR)
    assign_installer(db_session, deal, second, reason="Troca", actor=ACTOR)
    _installer_login(client)

    assert client.post(f"/prestador/instalacoes/{old.id}/resposta", data={"decisao": "aceita"}).status_code == 404


def test_the_admin_sees_the_installers_answer_and_a_declined_one_can_be_replaced(client, db_session):
    _admin(client, db_session)
    first, second = _installer(db_session, "Primeiro", "p@example.com"), _installer(db_session, "Segundo", "s@example.com")
    _, qualification, deal = _accepted(db_session)
    assignment = assign_installer(db_session, deal, first, reason="Atende", actor=ACTOR)
    respond_assignment(db_session, assignment, first, answer="recusada", reason="Agenda cheia")

    page = client.get(f"/admin/oportunidades/{qualification.id}").text
    assert "Agenda cheia" in page and "Recusada" in page

    client.post(f"/admin/oportunidades/{qualification.id}/instalador", data={"instalador": str(second.id), "motivo": "Próximo"})
    assert db_session.query(InstallerAssignment).filter_by(status=AssignmentStatus.PENDENTE).count() == 1


def test_the_buyer_sees_the_installer_only_after_the_installer_accepted(client, db_session):
    installer = _installer(db_session)
    buyer, _, deal = _accepted(db_session)
    buyer.set_password("senha-forte-123")
    buyer.email = "comprador@example.com"
    db_session.flush()
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    client.post("/comprador/login", data={"email": "comprador@example.com", "password": "senha-forte-123"})

    assert "Instalações Sul" not in client.get("/comprador/propostas").text

    respond_assignment(db_session, assignment, installer, answer="aceita", reason="")
    page = client.get("/comprador/propostas").text
    assert "Instalador responsável" in page and "Instalações Sul" in page


def test_the_installer_menu_has_the_installations_item(client, db_session):
    _installer(db_session)
    _installer_login(client)

    assert 'href="/prestador/instalacoes" aria-current="page"' in client.get("/prestador/instalacoes").text
