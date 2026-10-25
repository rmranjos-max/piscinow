from datetime import date, timedelta
from decimal import Decimal

from piscinow.matching.inbox import respond
from piscinow.matching.service import run_matching, save_profile, share_with_partners
from piscinow.models.matching import MatchingDecision
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.proposal import DealMessage, MessageAuthor, Proposal, ProposalStatus
from piscinow.models.qualification import DealEvent, DealStatus, FieldSource
from piscinow.proposals.rules import FEASIBILITY_ITEMS
from piscinow.proposals.service import post_message, save_feasibility, submit_proposal
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field

ITEMS = [("Piscina de fibra 7x3", Decimal("18000.00")), ("Instalação", Decimal("3000.00"))]


def _loja(db_session, name="Studio Fibra Sul", email="loja@example.com"):
    loja = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED, email=email)
    loja.set_password("senha-forte-123")
    db_session.add(loja)
    db_session.flush()
    save_profile(db_session, loja, areas="Valinhos", pool_types=["fibra"], budget_bands=[], capacity=5, active=True, actor="t")
    return loja


def _buyer_with_proposals(client, db_session, *stores, login=True, email="comprador@example.com"):
    buyer = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED, email=email,
        phone="(19) 99999-0000",
    )
    buyer.set_password("senha-forte-123")
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    deal = active_deal(db_session, buyer.id)
    run_matching(db_session, deal, actor="admin:x")
    share_with_partners(db_session, deal, actor="admin:x")
    proposals, decisions = {}, {}
    for store in stores:
        decision = db_session.query(MatchingDecision).filter_by(deal_id=deal.id, partner_member_id=store.id).one()
        respond(db_session, decision, answer="em_analise", reason="")
        proposals[store.id] = submit_proposal(
            db_session, decision, items=ITEMS, scope="Fornecimento e instalação completa",
            lead_time_days=45, valid_until=date.today() + timedelta(days=15), exclusions="Paisagismo",
        )
        decisions[store.id] = decision
    if login:
        client.post("/comprador/login", data={"email": email, "password": "senha-forte-123"})
    return buyer, deal, proposals, decisions


def _approve(db_session, deal, status="approved", **states):
    items = [{"key": k, "state": states.get(k, "ok"), "note": "Declive leve" if states.get(k) == "ressalva" else ""} for k in FEASIBILITY_ITEMS]
    save_feasibility(db_session, deal, status=status, items=items, notes="", actor="admin:equipe@piscinow.com.br")


def test_the_page_requires_a_comprador_login(client):
    response = client.get("/comprador/propostas", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/comprador/login"


def test_a_buyer_without_an_opportunity_is_pointed_to_the_consultor(client, db_session):
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Marina", status=MemberStatus.APPROVED, email="c@example.com")
    buyer.set_password("senha-forte-123")
    db_session.add(buyer)
    db_session.flush()
    client.post("/comprador/login", data={"email": "c@example.com", "password": "senha-forte-123"})

    page = client.get("/comprador/propostas")

    assert page.status_code == 200
    assert "/comprador/consultor" in page.text


def test_the_buyer_sees_each_store_identified_with_its_proposal_but_no_acceptance_before_viability(client, db_session):
    a, b = _loja(db_session, "Studio Fibra Sul", "a@example.com"), _loja(db_session, "Piscinas Campinas", "b@example.com")
    _buyer_with_proposals(client, db_session, a, b)

    page = client.get("/comprador/propostas")

    assert "Studio Fibra Sul" in page.text and "Piscinas Campinas" in page.text
    assert "R$ 21.000,00" in page.text
    assert "Paisagismo" in page.text
    assert "ainda não foi avaliada" in page.text
    assert "Aceitar esta proposta" not in page.text


def test_viability_with_caveats_is_shown_next_to_the_proposals_and_enables_acceptance(client, db_session):
    loja = _loja(db_session)
    _, deal, _, _ = _buyer_with_proposals(client, db_session, loja)
    _approve(db_session, deal, "conditionally_approved", terreno="ressalva")

    page = client.get("/comprador/propostas")

    assert "Aprovada com ressalvas" in page.text
    assert "Declive leve" in page.text
    assert "Aceitar esta proposta" in page.text


def test_accepting_requires_the_explicit_confirmation(client, db_session):
    loja = _loja(db_session)
    _, deal, proposals, _ = _buyer_with_proposals(client, db_session, loja)
    _approve(db_session, deal)

    response = client.post(f"/comprador/propostas/{proposals[loja.id].id}/aceitar", data={})

    assert response.status_code == 400
    assert proposals[loja.id].status == ProposalStatus.ENVIADA


def test_accepting_assigns_the_store_closes_the_others_and_releases_the_contact_only_to_it(client, db_session):
    a, b = _loja(db_session, "Studio Fibra Sul", "a@example.com"), _loja(db_session, "Piscinas Campinas", "b@example.com")
    buyer, deal, proposals, _ = _buyer_with_proposals(client, db_session, a, b)
    _approve(db_session, deal)

    response = client.post(
        f"/comprador/propostas/{proposals[a.id].id}/aceitar", data={"confirmo": "on"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert deal.status == DealStatus.ACCEPTED and deal.assigned_member_id == a.id
    assert proposals[a.id].status == ProposalStatus.ACEITA and proposals[b.id].status == ProposalStatus.ENCERRADA
    assert "Proposta aceita" in response.text
    assert db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="contact_released").count() == 1

    # The chosen store now sees the contact; the other store sees nothing at all.
    client.post("/comprador/logout")
    client.post("/loja/login", data={"email": "a@example.com", "password": "senha-forte-123"})
    mine = client.get("/loja/oportunidades").text
    assert "Marina Duarte" in mine and "(19) 99999-0000" in mine
    client.post("/loja/logout")
    client.post("/loja/login", data={"email": "b@example.com", "password": "senha-forte-123"})
    theirs = client.get("/loja/oportunidades").text
    assert "Marina" not in theirs and "99999-0000" not in theirs and "Cliente #" not in theirs


def test_accepting_with_a_rejected_viability_is_refused_with_the_reason(client, db_session):
    loja = _loja(db_session)
    _, deal, proposals, _ = _buyer_with_proposals(client, db_session, loja)
    items = [{"key": k, "state": "impeditivo", "note": ""} for k in FEASIBILITY_ITEMS]
    save_feasibility(db_session, deal, status="rejected", items=items, notes="Sem acesso", actor="admin:x")

    response = client.post(f"/comprador/propostas/{proposals[loja.id].id}/aceitar", data={"confirmo": "on"})

    assert response.status_code == 400
    assert "reprovada" in response.text
    assert deal.status == DealStatus.PROPOSAL_SENT


def test_the_buyer_can_reject_with_a_reason_and_without_one_it_is_refused(client, db_session):
    loja = _loja(db_session)
    _, _, proposals, _ = _buyer_with_proposals(client, db_session, loja)
    url = f"/comprador/propostas/{proposals[loja.id].id}/recusar"

    assert client.post(url, data={"motivo": " "}).status_code == 400
    client.post(url, data={"motivo": "Acima do orçamento"})

    assert proposals[loja.id].status == ProposalStatus.RECUSADA


def test_asking_for_a_revision_records_it_and_starts_the_negotiation(client, db_session):
    loja = _loja(db_session)
    _, deal, _, decisions = _buyer_with_proposals(client, db_session, loja)

    response = client.post(
        f"/comprador/propostas/loja/{decisions[loja.id].id}/revisao", data={"texto": "Consegue 30 dias?"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert deal.status == DealStatus.NEGOTIATING
    message = db_session.query(DealMessage).one()
    assert message.is_revision_request and message.author == MessageAuthor.COMPRADOR
    assert "Consegue 30 dias?" in response.text


def test_a_plain_message_does_not_start_the_negotiation(client, db_session):
    loja = _loja(db_session)
    _, deal, _, decisions = _buyer_with_proposals(client, db_session, loja)

    client.post(f"/comprador/propostas/loja/{decisions[loja.id].id}/mensagem", data={"texto": "Boa tarde"})

    assert deal.status == DealStatus.PROPOSAL_SENT
    assert db_session.query(DealMessage).one().is_revision_request is False


def test_an_expired_proposal_is_marked_and_cannot_be_accepted(client, db_session):
    loja = _loja(db_session)
    _, deal, proposals, _ = _buyer_with_proposals(client, db_session, loja)
    _approve(db_session, deal)
    proposals[loja.id].valid_until = date.today() - timedelta(days=1)
    db_session.flush()

    page = client.get("/comprador/propostas")
    response = client.post(f"/comprador/propostas/{proposals[loja.id].id}/aceitar", data={"confirmo": "on"})

    assert "Vencida" in page.text and "Aceitar esta proposta" not in page.text
    assert response.status_code == 400 and "vencida" in response.text


def test_a_buyer_cannot_touch_another_buyers_proposals_or_threads(client, db_session):
    loja = _loja(db_session)
    _, deal, proposals, decisions = _buyer_with_proposals(client, db_session, loja, login=False)
    _approve(db_session, deal)
    stranger = Member(profile_type=ProfileType.COMPRADOR, name="Outro", status=MemberStatus.APPROVED, email="x@example.com")
    stranger.set_password("senha-forte-123")
    db_session.add(stranger)
    db_session.flush()
    client.post("/comprador/login", data={"email": "x@example.com", "password": "senha-forte-123"})

    assert client.post(f"/comprador/propostas/{proposals[loja.id].id}/aceitar", data={"confirmo": "on"}).status_code == 404
    assert client.post(f"/comprador/propostas/{proposals[loja.id].id}/recusar", data={"motivo": "x"}).status_code == 404
    assert client.post(f"/comprador/propostas/loja/{decisions[loja.id].id}/revisao", data={"texto": "x"}).status_code == 404
    assert client.post(f"/comprador/propostas/loja/{decisions[loja.id].id}/mensagem", data={"texto": "x"}).status_code == 404
    assert proposals[loja.id].status == ProposalStatus.ENVIADA
    assert "Studio Fibra Sul" not in client.get("/comprador/propostas").text


def test_the_buyer_sees_the_store_reply_in_the_thread(client, db_session):
    loja = _loja(db_session)
    buyer, _, _, decisions = _buyer_with_proposals(client, db_session, loja)
    post_message(db_session, decisions[loja.id], author=MessageAuthor.LOJA, member=loja, text="Posso fazer em 35 dias.")

    assert "Posso fazer em 35 dias." in client.get("/comprador/propostas").text


def test_the_menu_and_home_show_the_proposals(client, db_session):
    loja = _loja(db_session)
    _buyer_with_proposals(client, db_session, loja)

    page = client.get("/comprador/propostas")
    home = client.get("/comprador")

    assert 'href="/comprador/propostas" aria-current="page"' in page.text
    assert "1 proposta" in home.text
