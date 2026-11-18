from decimal import Decimal

from piscinow.models.admin import AdminUser
from piscinow.models.payment import AllocationStatus, Payment, PaymentAllocation, PaymentStatus
from piscinow.models.project import Project
from piscinow.proposals.service import accept_proposal
from tests.proposals.test_service import _approve_feasibility, _loja, _send, _setup


def _admin(client, db_session):
    admin = AdminUser.create(email="equipe@piscinow.com.br", password="senha-forte-123")
    db_session.add(admin)
    db_session.flush()
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})


def _accepted_project(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])
    accept_proposal(db_session, proposal, buyer)
    project = db_session.query(Project).filter_by(member_id=buyer.id).one()
    return buyer, loja, proposal, project


def _phases(**values):
    return {f"fase_{k}": v for k, v in values.items()}


def test_an_accepted_proposal_shows_up_waiting_for_the_schedule_with_the_store_and_version(client, db_session):
    _admin(client, db_session)
    _accepted_project(db_session)

    page = client.get("/admin/pagamentos").text

    assert "Proposta v1 de Studio Fibra Sul" in page
    assert "Montar cronograma" in page


def test_the_schedule_form_shows_the_accepted_total_and_the_store(client, db_session):
    _admin(client, db_session)
    _, _, _, project = _accepted_project(db_session)

    page = client.get(f"/admin/pagamentos/{project.id}/cronograma").text

    assert "21.000,00" in page and "Studio Fibra Sul" in page
    assert 'name="fase_estrutura"' in page


def test_a_schedule_that_does_not_add_up_is_refused_with_the_reason_and_keeps_what_was_typed(client, db_session):
    _admin(client, db_session)
    _, _, _, project = _accepted_project(db_session)

    response = client.post(f"/admin/pagamentos/{project.id}/cronograma", data=_phases(estrutura="15000,00"))

    assert response.status_code == 400
    assert "igual ao total aceito" in response.text
    assert 'value="15000,00"' in response.text
    assert db_session.query(Payment).count() == 0


def test_a_malformed_amount_is_reported_for_its_phase(client, db_session):
    _admin(client, db_session)
    _, _, _, project = _accepted_project(db_session)

    response = client.post(f"/admin/pagamentos/{project.id}/cronograma", data=_phases(estrutura="21.000,00"))

    assert response.status_code == 400 and "Estrutura" in response.text


def test_the_whole_journey_from_acceptance_to_a_released_phase_pays_the_store(client, db_session):
    _admin(client, db_session)
    buyer, loja, proposal, project = _accepted_project(db_session)

    response = client.post(
        f"/admin/pagamentos/{project.id}/cronograma",
        data=_phases(terraplanagem="3000,00", estrutura="12000,00", revestimento="4000,00", acabamento="2000,00"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    payment = db_session.query(Payment).one()
    assert payment.total_amount == Decimal("21000.00") == proposal.total

    client.post("/admin/logout")
    buyer.set_password("senha-forte-123")
    buyer.email = "comprador.jornada@example.com"
    db_session.flush()
    client.post("/comprador/login", data={"email": "comprador.jornada@example.com", "password": "senha-forte-123"})
    client.post("/comprador/projeto/pagamento/pagar")
    assert payment.status == PaymentStatus.PAGO

    client.post("/comprador/logout")
    client.post("/admin/login", data={"email": "equipe@piscinow.com.br", "password": "senha-forte-123"})
    client.post(f"/admin/pagamentos/{payment.id}/fases/terraplanagem/liberar")

    released = db_session.query(PaymentAllocation).filter_by(payment_id=payment.id, status=AllocationStatus.LIBERADO).all()
    assert [(a.stage.value, a.recipient_member_id, a.amount) for a in released] == [("terraplanagem", loja.id, Decimal("3000.00"))]
