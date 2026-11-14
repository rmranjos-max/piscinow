import pytest

from piscinow.installation.service import (
    InstallationError, assign_installer, candidate_installers, inbox_for_installer, respond_assignment,
    responsible_installer, save_installer_profile,
)
from piscinow.models.installation import AssignmentStatus, InstallerAssignment
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import DealEvent, DealStatus
from piscinow.proposals.service import accept_proposal
from tests.proposals.test_service import _approve_feasibility, _loja, _send, _setup

ACTOR = "admin:equipe@piscinow.com.br"


def _installer(db_session, name="Instalações Sul", *, areas="Valinhos", kinds=("instalacao",), approved=True, profile=True):
    member = Member(
        profile_type=ProfileType.PRESTADOR, name=name, status=MemberStatus.APPROVED if approved else MemberStatus.WAITLISTED,
        email=f"{name[:5].lower()}@example.com", phone="(19) 98888-7777",
    )
    db_session.add(member)
    db_session.flush()
    if profile:
        save_installer_profile(db_session, member, areas=areas, service_kinds=list(kinds), active=True, actor=ACTOR)
    return member


def _accepted_deal(db_session):
    loja = _loja(db_session)
    buyer, _, deal, decisions = _setup(db_session, loja)
    _approve_feasibility(db_session, deal)
    proposal = _send(db_session, decisions[loja.id])
    accept_proposal(db_session, proposal, buyer)
    return buyer, deal, loja, proposal


def test_the_profile_cleans_the_cities_and_validates_the_kinds(db_session):
    installer = _installer(db_session, areas="Valinhos,  campinas\nValinhos", kinds=("instalacao", "reparo"))

    from piscinow.installation.service import get_installer_profile
    profile = get_installer_profile(db_session, installer.id)
    assert profile.service_areas == ["Valinhos", "campinas"]
    assert profile.service_kinds == ["instalacao", "reparo"]
    assert profile.updated_by == ACTOR


@pytest.mark.parametrize("args", [dict(kinds=("limpeza",)), dict(kinds=()), dict(areas=" , ")])
def test_an_invalid_installer_profile_is_rejected(db_session, args):
    with pytest.raises(InstallationError):
        _installer(db_session, **args)


def test_only_an_accepted_deal_can_get_an_installer(db_session):
    loja = _loja(db_session)
    _, _, deal, _ = _setup(db_session, loja)
    installer = _installer(db_session)

    assert deal.status != DealStatus.ACCEPTED
    with pytest.raises(InstallationError):
        assign_installer(db_session, deal, installer, reason="Atende a região", actor=ACTOR)


def test_assigning_needs_a_reason_and_an_approved_installer(db_session):
    _, deal, _, _ = _accepted_deal(db_session)

    with pytest.raises(InstallationError):
        assign_installer(db_session, deal, _installer(db_session), reason="  ", actor=ACTOR)
    with pytest.raises(InstallationError):
        assign_installer(db_session, deal, _installer(db_session, "Pendente", approved=False), reason="Ok", actor=ACTOR)
    buyer = Member(profile_type=ProfileType.COMPRADOR, name="Outro", status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()
    with pytest.raises(InstallationError):
        assign_installer(db_session, deal, buyer, reason="Ok", actor=ACTOR)
    assert db_session.query(InstallerAssignment).count() == 0


def test_a_valid_assignment_is_pending_and_recorded_in_the_history(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer = _installer(db_session)

    assignment = assign_installer(db_session, deal, installer, reason="Atende Valinhos", actor=ACTOR)

    assert assignment.status == AssignmentStatus.PENDENTE
    assert (assignment.assigned_by, assignment.assigned_reason) == (ACTOR, "Atende Valinhos")
    event = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="installer_assigned").one()
    assert "Instalações Sul" in event.note and event.actor == ACTOR


def test_reassigning_cancels_the_previous_assignment_with_a_reason(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    first, second = _installer(db_session, "Primeiro"), _installer(db_session, "Segundo")
    old = assign_installer(db_session, deal, first, reason="Primeira escolha", actor=ACTOR)

    new = assign_installer(db_session, deal, second, reason="Primeiro sem agenda", actor=ACTOR)

    assert old.status == AssignmentStatus.CANCELADA
    assert old.cancel_reason == "Reatribuída: Primeiro sem agenda" and old.cancelled_at is not None
    assert new.status == AssignmentStatus.PENDENTE


def test_candidates_put_the_installers_that_serve_the_city_first_and_say_why_others_do_not(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    _installer(db_session, "Longe", areas="Sorocaba")
    _installer(db_session, "Sem Perfil", profile=False)
    _installer(db_session, "Perto", areas="Valinhos, Campinas")

    names = [(c["member"].name, c["note"]) for c in candidate_installers(db_session, deal)]

    assert names[0] == ("Perto", "Atende Valinhos")
    assert ("Longe", "Não atende Valinhos") in names
    assert ("Sem Perfil", "Sem perfil de atendimento") in names


def test_candidates_exclude_installers_that_are_not_approved(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    _installer(db_session, "Pendente", approved=False)

    assert candidate_installers(db_session, deal) == []


def test_the_installer_accepts_and_the_acceptance_is_final(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer = _installer(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)

    respond_assignment(db_session, assignment, installer, answer="aceita", reason="")

    assert assignment.status == AssignmentStatus.ACEITA and assignment.responded_at is not None
    with pytest.raises(InstallationError):
        respond_assignment(db_session, assignment, installer, answer="recusada", reason="Mudei de ideia")
    assert db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="installer_response").count() == 1


def test_declining_needs_a_reason_and_frees_the_deal_for_a_new_assignment(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer, other = _installer(db_session), _installer(db_session, "Outro")
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)

    with pytest.raises(InstallationError):
        respond_assignment(db_session, assignment, installer, answer="recusada", reason=" ")
    respond_assignment(db_session, assignment, installer, answer="recusada", reason="Agenda cheia")

    assert (assignment.status, assignment.response_reason) == (AssignmentStatus.RECUSADA, "Agenda cheia")
    assert assign_installer(db_session, deal, other, reason="Próximo da lista", actor=ACTOR).status == AssignmentStatus.PENDENTE


def test_an_installer_cannot_answer_someone_elses_assignment(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer, other = _installer(db_session), _installer(db_session, "Outro")
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)

    with pytest.raises(InstallationError):
        respond_assignment(db_session, assignment, other, answer="aceita", reason="")
    assert assignment.status == AssignmentStatus.PENDENTE


def test_an_invalid_answer_is_refused(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer = _installer(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)

    for answer in ("pendente", "cancelada", "talvez"):
        with pytest.raises(InstallationError):
            respond_assignment(db_session, assignment, installer, answer=answer, reason="x")


def test_the_inbox_shows_the_project_without_price_or_contact_until_the_installer_accepts(db_session):
    buyer, deal, loja, proposal = _accepted_deal(db_session)
    installer = _installer(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)

    [item] = inbox_for_installer(db_session, installer.id)

    assert item["contact"] is None
    assert item["briefing"]["codigo"].startswith("Cliente #")
    assert item["store"] == "Studio Fibra Sul"
    assert item["scope"] == proposal.scope and item["lead_time_days"] == proposal.lead_time_days
    assert "total" not in item and "price" not in item
    assert "Marina" not in repr({k: v for k, v in item.items() if k != "assignment"})

    respond_assignment(db_session, assignment, installer, answer="aceita", reason="")
    [accepted] = inbox_for_installer(db_session, installer.id)
    assert accepted["contact"] == {"nome": "Marina Duarte", "email": "marina@example.com", "telefone": "(19) 99999-0000", "regiao": None}


def test_the_inbox_is_private_to_each_installer_and_hides_cancelled_assignments(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    first, second = _installer(db_session, "Primeiro"), _installer(db_session, "Segundo")
    assign_installer(db_session, deal, first, reason="Atende", actor=ACTOR)
    assert len(inbox_for_installer(db_session, first.id)) == 1 and inbox_for_installer(db_session, second.id) == []

    assign_installer(db_session, deal, second, reason="Troca", actor=ACTOR)

    assert inbox_for_installer(db_session, first.id) == []
    assert len(inbox_for_installer(db_session, second.id)) == 1


def test_a_declined_assignment_stays_visible_as_history_without_contact(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer = _installer(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    respond_assignment(db_session, assignment, installer, answer="recusada", reason="Agenda cheia")

    [item] = inbox_for_installer(db_session, installer.id)

    assert item["assignment"].status == AssignmentStatus.RECUSADA and item["contact"] is None


def test_a_lost_deal_leaves_the_installer_inbox(db_session):
    from piscinow.qualification.deals import mark_lost

    _, deal, _, _ = _accepted_deal(db_session)
    installer = _installer(db_session)
    assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)

    mark_lost(db_session, deal, reason="Comprador desistiu", actor=ACTOR)

    assert inbox_for_installer(db_session, installer.id) == []


def test_the_buyer_only_sees_the_installer_after_the_installer_accepted(db_session):
    _, deal, _, _ = _accepted_deal(db_session)
    installer = _installer(db_session)
    assignment = assign_installer(db_session, deal, installer, reason="Atende", actor=ACTOR)
    assert responsible_installer(db_session, deal) is None

    respond_assignment(db_session, assignment, installer, answer="aceita", reason="")

    assert responsible_installer(db_session, deal).name == "Instalações Sul"
