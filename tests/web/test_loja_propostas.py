from datetime import date, timedelta
from decimal import Decimal

from piscinow.matching.inbox import respond
from piscinow.matching.service import run_matching, save_profile, share_with_partners
from piscinow.models.matching import MatchingDecision
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.proposal import DealMessage, MessageAuthor, Proposal, ProposalStatus
from piscinow.models.qualification import DealStatus, FieldSource
from piscinow.proposals.service import post_message
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field

BUYER_EMAIL = "marina.contato@example.com"
BUYER_PHONE = "(19) 99999-0000"


def _loja(db_session, name="Studio Fibra Sul", email="loja@example.com"):
    loja = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED, email=email)
    loja.set_password("senha-forte-123")
    db_session.add(loja)
    db_session.flush()
    save_profile(db_session, loja, areas="Valinhos", pool_types=["fibra"], budget_bands=[], capacity=5, active=True, actor="t")
    return loja


def _login(client, email="loja@example.com"):
    client.post("/loja/login", data={"email": email, "password": "senha-forte-123"})


def _shared(db_session, *stores, analyze=True):
    buyer = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED,
        email=BUYER_EMAIL, phone=BUYER_PHONE,
    )
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    deal = active_deal(db_session, buyer.id)
    run_matching(db_session, deal, actor="admin:x")
    share_with_partners(db_session, deal, actor="admin:x")
    decisions = {s.id: db_session.query(MatchingDecision).filter_by(deal_id=deal.id, partner_member_id=s.id).one() for s in stores}
    if analyze:
        for decision in decisions.values():
            respond(db_session, decision, answer="em_analise", reason="")
    return buyer, deal, decisions


def _form(**overrides):
    data = {
        "item_desc": ["Piscina de fibra 7x3", "Instalação", "", ""],
        "item_amount": ["18000,00", "3000", "", ""],
        "scope": "Fornecimento e instalação completa",
        "lead_time_days": "45",
        "valid_until": (date.today() + timedelta(days=15)).isoformat(),
        "exclusions": "Paisagismo",
    }
    return {**data, **overrides}


def test_the_proposal_form_only_appears_after_the_store_said_it_will_analyze(client, db_session):
    loja = _loja(db_session)
    _shared(db_session, loja, analyze=False)
    _login(client)

    assert "Enviar proposta" not in client.get("/loja/oportunidades").text


def test_after_analyzing_the_store_sees_the_proposal_form(client, db_session):
    loja = _loja(db_session)
    _shared(db_session, loja)
    _login(client)

    page = client.get("/loja/oportunidades")

    assert "Enviar proposta" in page.text
    assert 'name="item_desc"' in page.text


def test_sending_a_proposal_saves_the_version_and_shows_it_with_the_total(client, db_session):
    loja = _loja(db_session)
    _, deal, decisions = _shared(db_session, loja)
    _login(client)

    response = client.post(f"/loja/oportunidades/{decisions[loja.id].id}/proposta", data=_form(), follow_redirects=True)

    assert response.status_code == 200
    proposal = db_session.query(Proposal).one()
    assert (proposal.version, proposal.total, proposal.lead_time_days) == (1, Decimal("21000.00"), 45)
    assert [i.description for i in proposal.items] == ["Piscina de fibra 7x3", "Instalação"]
    assert deal.status == DealStatus.PROPOSAL_SENT
    assert "R$ 21.000,00" in response.text
    assert "Versão 1" in response.text


def test_a_second_submission_creates_version_two_and_keeps_version_one_visible(client, db_session):
    loja = _loja(db_session)
    _, _, decisions = _shared(db_session, loja)
    _login(client)
    url = f"/loja/oportunidades/{decisions[loja.id].id}/proposta"
    client.post(url, data=_form())

    response = client.post(url, data=_form(item_desc=["Tudo incluso"], item_amount=["19500"]), follow_redirects=True)

    assert "Versão 2" in response.text and "Versão 1" in response.text
    assert "Substituída" in response.text
    assert db_session.query(Proposal).filter_by(status=ProposalStatus.ENVIADA).count() == 1


def test_an_invalid_proposal_shows_every_error_and_saves_nothing(client, db_session):
    loja = _loja(db_session)
    _, _, decisions = _shared(db_session, loja)
    _login(client)

    response = client.post(
        f"/loja/oportunidades/{decisions[loja.id].id}/proposta",
        data=_form(item_desc=["", ""], item_amount=["", ""], scope="", lead_time_days="0",
                   valid_until=date.today().isoformat()),
    )

    assert response.status_code == 400
    assert "Inclua ao menos um item" in response.text
    assert "Descreva o escopo" in response.text
    assert "prazo estimado" in response.text
    assert "validade deve ser uma data futura" in response.text
    assert db_session.query(Proposal).count() == 0


def test_text_that_is_not_a_number_or_a_date_is_reported_before_the_business_rules(client, db_session):
    loja = _loja(db_session)
    _, _, decisions = _shared(db_session, loja)
    _login(client)

    response = client.post(
        f"/loja/oportunidades/{decisions[loja.id].id}/proposta", data=_form(lead_time_days="abc", valid_until="ontem")
    )

    assert response.status_code == 400
    assert "só com números" in response.text and "como uma data" in response.text
    assert db_session.query(Proposal).count() == 0


def test_a_malformed_amount_is_reported_not_guessed(client, db_session):
    loja = _loja(db_session)
    _, _, decisions = _shared(db_session, loja)
    _login(client)

    response = client.post(
        f"/loja/oportunidades/{decisions[loja.id].id}/proposta",
        data=_form(item_desc=["Piscina"], item_amount=["18.000,50"]),
    )

    assert response.status_code == 400
    assert "valor" in response.text.lower()
    assert db_session.query(Proposal).count() == 0


def test_an_item_with_a_description_but_no_amount_is_an_error(client, db_session):
    loja = _loja(db_session)
    _, _, decisions = _shared(db_session, loja)
    _login(client)

    response = client.post(
        f"/loja/oportunidades/{decisions[loja.id].id}/proposta",
        data=_form(item_desc=["Piscina", "Brinde"], item_amount=["18000", ""]),
    )

    assert response.status_code == 400


def test_a_store_cannot_send_a_proposal_for_another_stores_opportunity(client, db_session):
    mine, other = _loja(db_session, "Minha", "minha@example.com"), _loja(db_session, "Outra", "outra@example.com")
    _, _, decisions = _shared(db_session, mine, other)
    _login(client, "minha@example.com")

    response = client.post(f"/loja/oportunidades/{decisions[other.id].id}/proposta", data=_form())

    assert response.status_code == 404
    assert db_session.query(Proposal).count() == 0


def test_the_store_sees_the_buyers_revision_request_in_the_conversation_and_can_reply(client, db_session):
    loja = _loja(db_session)
    buyer, _, decisions = _shared(db_session, loja)
    _login(client)
    client.post(f"/loja/oportunidades/{decisions[loja.id].id}/proposta", data=_form())
    post_message(db_session, decisions[loja.id], author=MessageAuthor.COMPRADOR, member=buyer,
                 text="Consegue reduzir o prazo?", revision=True)

    page = client.get("/loja/oportunidades")
    assert "Consegue reduzir o prazo?" in page.text
    assert "Pedido de revisão" in page.text

    client.post(f"/loja/oportunidades/{decisions[loja.id].id}/mensagem", data={"texto": "Consigo em 35 dias."})
    assert db_session.query(DealMessage).filter_by(author=MessageAuthor.LOJA).one().text == "Consigo em 35 dias."


def test_an_empty_reply_is_refused_and_another_stores_thread_is_unreachable(client, db_session):
    mine, other = _loja(db_session, "Minha", "minha@example.com"), _loja(db_session, "Outra", "outra@example.com")
    _, _, decisions = _shared(db_session, mine, other)
    _login(client, "minha@example.com")

    assert client.post(f"/loja/oportunidades/{decisions[mine.id].id}/mensagem", data={"texto": "  "}).status_code == 400
    assert client.post(f"/loja/oportunidades/{decisions[other.id].id}/mensagem", data={"texto": "oi"}).status_code == 404


def test_before_the_acceptance_the_proposal_page_shows_no_buyer_contact(client, db_session):
    loja = _loja(db_session)
    _, _, decisions = _shared(db_session, loja)
    _login(client)
    client.post(f"/loja/oportunidades/{decisions[loja.id].id}/proposta", data=_form())

    page = client.get("/loja/oportunidades").text

    for secret in ("Marina", "Duarte", BUYER_EMAIL, BUYER_PHONE):
        assert secret not in page


def test_an_item_can_use_a_catalog_product_and_the_buyer_then_sees_its_photo(client, db_session):
    import io as _io
    from PIL import Image
    from piscinow.media.photos import add_photo
    from piscinow.media.storage import MemoryMediaStorage
    from piscinow.models.product import Product, ProductKind

    storage = MemoryMediaStorage()
    client.app.state.media_storage = storage
    loja = _loja(db_session)
    buyer, _, decisions = _shared(db_session, loja)
    product = Product(member_id=loja.id, kind=ProductKind.PISCINA, category="fibra", name="Piscina Fibra 7x3", price=18000)
    db_session.add(product)
    db_session.flush()
    buffer = _io.BytesIO()
    Image.new("RGB", (600, 400), (20, 110, 170)).save(buffer, "JPEG")
    photo = add_photo(db_session, storage, product, buffer.getvalue())
    _login(client)

    assert "Piscina Fibra 7x3" in client.get("/loja/oportunidades").text  # offered in the catalog choice
    response = client.post(
        f"/loja/oportunidades/{decisions[loja.id].id}/proposta",
        data=_form(item_desc=["", ""], item_amount=["", ""], item_product=[str(product.id), ""]), follow_redirects=True,
    )

    assert response.status_code == 200
    proposal = db_session.query(Proposal).one()
    assert proposal.items[0].product_id == product.id and proposal.total == Decimal("18000.00")
    assert f'src="/midia/{photo.thumb_key}"' in response.text

    buyer.set_password("senha-forte-123")
    buyer.email = "comprador.foto@example.com"
    db_session.flush()
    client.post("/loja/logout")
    client.post("/comprador/login", data={"email": "comprador.foto@example.com", "password": "senha-forte-123"})
    page = client.get("/comprador/propostas").text
    assert f'src="/midia/{photo.thumb_key}"' in page and 'alt="Foto de Piscina Fibra 7x3"' in page


def test_a_store_cannot_put_another_stores_product_in_its_proposal(client, db_session):
    from piscinow.models.product import Product, ProductKind

    mine, other = _loja(db_session, "Minha", "minha@example.com"), _loja(db_session, "Outra", "outra@example.com")
    _, _, decisions = _shared(db_session, mine, other)
    foreign = Product(member_id=other.id, kind=ProductKind.PISCINA, category="fibra", name="Produto Alheio", price=1000)
    db_session.add(foreign)
    db_session.flush()
    _login(client, "minha@example.com")

    page = client.get("/loja/oportunidades").text
    response = client.post(
        f"/loja/oportunidades/{decisions[mine.id].id}/proposta",
        data=_form(item_desc=[""], item_amount=[""], item_product=[str(foreign.id)]),
    )

    assert "Produto Alheio" not in page
    assert response.status_code == 400 and "não está no seu catálogo" in response.text
    assert db_session.query(Proposal).count() == 0
