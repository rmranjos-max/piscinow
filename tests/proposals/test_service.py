from datetime import date, timedelta
from decimal import Decimal

import pytest

from piscinow.matching.inbox import inbox_for_partner, respond
from piscinow.matching.service import run_matching, save_profile, share_with_partners
from piscinow.models.matching import MatchingDecision, PartnerResponse
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.proposal import DealMessage, MessageAuthor, Proposal, ProposalStatus
from piscinow.models.qualification import DealEvent, DealStatus, FieldSource
from piscinow.proposals.service import (
    ProposalError, accept_proposal, post_message, reject_proposal, save_feasibility, submit_proposal,
)
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field

TODAY = date.today()
ITEMS = [("Piscina de fibra 7x3", Decimal("18000.00")), ("Instalação", Decimal("3000.00"))]


def _loja(db_session, name="Studio Fibra Sul"):
    loja = Member(profile_type=ProfileType.LOJA, name=name, status=MemberStatus.APPROVED)
    db_session.add(loja)
    db_session.flush()
    save_profile(db_session, loja, areas="Valinhos", pool_types=["fibra"], budget_bands=[], capacity=5, active=True, actor="t")
    return loja


def _setup(db_session, *stores):
    buyer = Member(
        profile_type=ProfileType.COMPRADOR, name="Marina Duarte", status=MemberStatus.APPROVED,
        email="marina@example.com", phone="(19) 99999-0000",
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
    decisions = {
        s.id: db_session.query(MatchingDecision).filter_by(deal_id=deal.id, partner_member_id=s.id).one() for s in stores
    }
    for decision in decisions.values():
        respond(db_session, decision, answer="em_analise", reason="")
    return buyer, qualification, deal, decisions


def _send(db_session, decision, items=ITEMS, **overrides):
    values = dict(scope="Fornecimento e instalação", lead_time_days=45, valid_until=TODAY + timedelta(days=15), exclusions="Paisagismo")
    return submit_proposal(db_session, decision, items=items, **{**values, **overrides})


def _approve_feasibility(db_session, deal, status="approved"):
    from piscinow.proposals.rules import FEASIBILITY_ITEMS

    items = [{"key": k, "state": "ok", "note": ""} for k in FEASIBILITY_ITEMS]
    save_feasibility(db_session, deal, status=status, items=items, notes="", actor="admin:equipe@piscinow.com.br")


def test_a_proposal_total_is_the_sum_of_items_and_the_deal_moves_to_proposal_sent(db_session):
    loja = _loja(db_session)
    _, _, deal, decisions = _setup(db_session, loja)

    proposal = _send(db_session, decisions[loja.id])

    assert (proposal.version, proposal.status) == (1, ProposalStatus.ENVIADA)
    assert proposal.total == Decimal("21000.00")
    assert [(i.position, i.description) for i in proposal.items] == [(1, "Piscina de fibra 7x3"), (2, "Instalação")]
    assert deal.status == DealStatus.PROPOSAL_SENT
    event = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="proposal_sent").one()
    assert "Studio Fibra Sul" in event.note and "v1" in event.note


def test_a_new_version_supersedes_the_previous_one_and_keeps_it_unchanged(db_session):
    loja = _loja(db_session)
    _, _, deal, decisions = _setup(db_session, loja)
    first = _send(db_session, decisions[loja.id])

    second = _send(db_session, decisions[loja.id], items=[("Tudo incluso", Decimal("19500.00"))])

    assert second.version == 2
    assert first.status == ProposalStatus.SUBSTITUIDA
    assert (first.total, len(first.items)) == (Decimal("21000.00"), 2)
    assert second.total == Decimal("19500.00")


def test_an_invalid_proposal_is_refused_with_every_reason_and_saves_nothing(db_session):
    loja = _loja(db_session)
    _, _, deal, decisions = _setup(db_session, loja)

    with pytest.raises(ProposalError) as raised:
        _send(db_session, decisions[loja.id], items=[], scope=" ", lead_time_days=0)

    assert len(raised.value.errors) == 3
    assert db_session.query(Proposal).count() == 0
    assert deal.status == DealStatus.PARTNER_REVIEW


def test_a_store_that_has_not_said_it_will_analyze_cannot_propose(db_session):
    loja = _loja(db_session)
    buyer, qualification, deal, decisions = _setup(db_session, loja)
    decisions[loja.id].response = PartnerResponse.PENDENTE

    with pytest.raises(ProposalError):
        _send(db_session, decisions[loja.id])


def test_a_store_that_declined_cannot_propose(db_session):
    loja = _loja(db_session)
    _, _, _, decisions = _setup(db_session, loja)
    respond(db_session, decisions[loja.id], answer="recusada", reason="Sem agenda")

    with pytest.raises(ProposalError):
        _send(db_session, decisions[loja.id])


def test_a_store_cannot_propose_after_the_buyer_withdrew_the_authorization(db_session):
    loja = _loja(db_session)
    _, qualification, _, decisions = _setup(db_session, loja)
    set_consent(db_session, qualification, False)

    with pytest.raises(ProposalError):
        _send(db_session, decisions[loja.id])


def test_the_buyer_can_message_and_ask_for_a_revision_which_starts_the_negotiation(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _send(db_session, decisions[loja.id])

    post_message(db_session, decisions[loja.id], author=MessageAuthor.COMPRADOR, member=buyer,
                 text="Consegue reduzir o prazo para 30 dias?", revision=True)

    assert deal.status == DealStatus.NEGOTIATING
    message = db_session.query(DealMessage).one()
    assert (message.is_revision_request, message.author, message.partner_member_id) == (True, MessageAuthor.COMPRADOR, loja.id)
    assert db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="revision_requested").count() == 1


def test_a_plain_message_does_not_change_the_deal_state_and_empty_messages_are_refused(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _send(db_session, decisions[loja.id])

    post_message(db_session, decisions[loja.id], author=MessageAuthor.COMPRADOR, member=buyer, text="Boa tarde!")
    with pytest.raises(ProposalError):
        post_message(db_session, decisions[loja.id], author=MessageAuthor.COMPRADOR, member=buyer, text="   ")

    assert deal.status == DealStatus.PROPOSAL_SENT


def test_only_the_buyer_can_flag_a_revision_request(db_session):
    loja = _loja(db_session)
    _, _, _, decisions = _setup(db_session, loja)

    with pytest.raises(ProposalError):
        post_message(db_session, decisions[loja.id], author=MessageAuthor.LOJA, member=loja, text="Revise!", revision=True)


def test_rejecting_a_proposal_needs_a_reason_and_keeps_the_deal_open_for_a_new_version(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    proposal = _send(db_session, decisions[loja.id])

    with pytest.raises(ProposalError):
        reject_proposal(db_session, proposal, buyer, reason=" ")
    reject_proposal(db_session, proposal, buyer, reason="Valor acima do orçamento")

    assert proposal.status == ProposalStatus.RECUSADA
    assert proposal.decision_reason == "Valor acima do orçamento"
    assert _send(db_session, decisions[loja.id]).version == 2


def test_accepting_needs_an_approved_viability(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    proposal = _send(db_session, decisions[loja.id])

    with pytest.raises(ProposalError) as raised:
        accept_proposal(db_session, proposal, buyer)
    assert "ainda não foi avaliada" in raised.value.errors[0]

    save_feasibility(db_session, deal, status="rejected", items=[{"key": k, "state": "impeditivo", "note": ""} for k in
                     ["acesso", "terreno", "escavacao", "hidraulica_eletrica", "medidas", "visita"]],
                     notes="Sem acesso para equipamentos", actor="admin:x")
    with pytest.raises(ProposalError) as raised:
        accept_proposal(db_session, proposal, buyer)
    assert "reprovada" in raised.value.errors[0]
    assert deal.status == DealStatus.PROPOSAL_SENT


def test_accepting_records_the_terms_assigns_the_store_and_closes_the_other_proposals(db_session):
    chosen, other = _loja(db_session, "Studio Fibra Sul"), _loja(db_session, "Outra Loja")
    buyer, _, deal, decisions = _setup(db_session, chosen, other)
    _approve_feasibility(db_session, deal, "conditionally_approved")
    winning = _send(db_session, decisions[chosen.id])
    losing = _send(db_session, decisions[other.id], items=[("Tudo", Decimal("25000.00"))])

    accept_proposal(db_session, winning, buyer)

    assert winning.status == ProposalStatus.ACEITA and winning.decided_at is not None
    assert losing.status == ProposalStatus.ENCERRADA
    assert deal.status == DealStatus.ACCEPTED
    assert deal.assigned_member_id == chosen.id
    accepted = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="proposal_accepted").one()
    assert accepted.actor == f"comprador:{buyer.id}" and "v1" in accepted.note and "21.000,00" in accepted.note
    assert db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="contact_released").count() == 1


def test_only_the_latest_open_version_can_be_accepted(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    first = _send(db_session, decisions[loja.id])
    _send(db_session, decisions[loja.id], items=[("Revisada", Decimal("19000.00"))])

    with pytest.raises(ProposalError):
        accept_proposal(db_session, first, buyer)


def test_an_expired_proposal_cannot_be_accepted(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])

    with pytest.raises(ProposalError) as raised:
        accept_proposal(db_session, proposal, buyer, today=TODAY + timedelta(days=16))
    assert "vencida" in raised.value.errors[0]


def test_a_buyer_cannot_accept_a_proposal_of_someone_elses_deal(db_session):
    loja = _loja(db_session)
    _, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])
    stranger = Member(profile_type=ProfileType.COMPRADOR, name="Outro", status=MemberStatus.APPROVED)
    db_session.add(stranger)
    db_session.flush()

    with pytest.raises(ProposalError):
        accept_proposal(db_session, proposal, stranger)


def test_an_accepted_deal_cannot_be_accepted_twice(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])
    accept_proposal(db_session, proposal, buyer)

    with pytest.raises(ProposalError):
        accept_proposal(db_session, proposal, buyer)


def test_after_the_acceptance_the_contact_goes_only_to_the_chosen_store_and_the_others_lose_access(db_session):
    chosen, other = _loja(db_session, "Studio Fibra Sul"), _loja(db_session, "Outra Loja")
    buyer, _, deal, decisions = _setup(db_session, chosen, other)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[chosen.id])
    assert inbox_for_partner(db_session, chosen.id)[0]["contact"] is None

    accept_proposal(db_session, proposal, buyer)

    [mine] = inbox_for_partner(db_session, chosen.id)
    assert mine["contact"] == {"nome": "Marina Duarte", "email": "marina@example.com", "telefone": "(19) 99999-0000", "regiao": None}
    assert inbox_for_partner(db_session, other.id) == []


def test_viability_saves_one_row_per_deal_with_who_decided_and_when(db_session):
    loja = _loja(db_session)
    _, _, deal, _ = _setup(db_session, loja)

    _approve_feasibility(db_session, deal)
    _approve_feasibility(db_session, deal, "approved")

    from piscinow.models.proposal import FeasibilityCheck
    check = db_session.query(FeasibilityCheck).one()
    assert check.status.value == "approved"
    assert check.decided_by == "admin:equipe@piscinow.com.br" and check.decided_at is not None


def test_an_inconsistent_viability_decision_is_refused(db_session):
    loja = _loja(db_session)
    _, _, deal, _ = _setup(db_session, loja)

    with pytest.raises(ProposalError):
        save_feasibility(db_session, deal, status="approved",
                         items=[{"key": k, "state": "pendente", "note": ""} for k in
                                ["acesso", "terreno", "escavacao", "hidraulica_eletrica", "medidas", "visita"]],
                         notes="", actor="admin:x")


def test_only_the_owner_can_reject_and_only_while_the_opportunity_is_open_and_visible(db_session):
    loja = _loja(db_session)
    buyer, qualification, deal, decisions = _setup(db_session, loja)
    proposal = _send(db_session, decisions[loja.id])
    stranger = Member(profile_type=ProfileType.COMPRADOR, name="Outro", status=MemberStatus.APPROVED)
    db_session.add(stranger)
    db_session.flush()

    with pytest.raises(ProposalError):
        reject_proposal(db_session, proposal, stranger, reason="Não gostei")
    assert proposal.status == ProposalStatus.ENVIADA

    set_consent(db_session, qualification, False)  # the buyer withdraws: the deal is cancelled
    with pytest.raises(ProposalError):
        reject_proposal(db_session, proposal, buyer, reason="Desisti")


def test_no_conversation_exists_with_a_store_that_has_not_agreed_to_analyze_or_that_declined(db_session):
    pending, declined = _loja(db_session, "Pendente"), _loja(db_session, "Recusou")
    buyer, _, deal, decisions = _setup(db_session, pending, declined)
    decisions[pending.id].response = PartnerResponse.PENDENTE
    respond(db_session, decisions[declined.id], answer="recusada", reason="Sem agenda")

    for store in (pending, declined):
        with pytest.raises(ProposalError):
            post_message(db_session, decisions[store.id], author=MessageAuthor.COMPRADOR, member=buyer, text="Olá?")
        with pytest.raises(ProposalError):
            post_message(db_session, decisions[store.id], author=MessageAuthor.LOJA, member=store, text="Olá?")
    assert db_session.query(DealMessage).count() == 0
