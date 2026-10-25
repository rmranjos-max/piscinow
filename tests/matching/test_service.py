import pytest

from piscinow.matching.service import (
    ProfileError,
    open_load,
    run_matching,
    save_profile,
    set_override,
    share_with_partners,
)
from piscinow.models.matching import MatchingDecision, MatchOverride
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import DealEvent, DealStatus, FieldSource
from piscinow.qualification.deals import active_deal
from piscinow.qualification.service import get_or_create_qualification, set_consent, set_field

BUYER = {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}


def _deal(db_session, name="Marina Duarte", **values):
    buyer = Member(profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED)
    db_session.add(buyer)
    db_session.flush()
    qualification = get_or_create_qualification(db_session, buyer)
    for key, value in {**BUYER, **values}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    set_consent(db_session, qualification, True)
    return active_deal(db_session, buyer.id)


def _loja(db_session, name="Studio Fibra Sul", *, approved=True, profile=True, **profile_args):
    loja = Member(
        profile_type=ProfileType.LOJA, name=name,
        status=MemberStatus.APPROVED if approved else MemberStatus.WAITLISTED,
    )
    db_session.add(loja)
    db_session.flush()
    if profile:
        args = dict(areas="Valinhos, Campinas", pool_types=["fibra"], budget_bands=[], capacity=3, active=True)
        save_profile(db_session, loja, **{**args, **profile_args}, actor="admin:equipe@piscinow.com.br")
    return loja


def _decisions(db_session, deal):
    return {
        d.partner_member_id: d for d in db_session.query(MatchingDecision).filter_by(deal_id=deal.id)
    }


def test_saving_a_profile_cleans_the_cities_and_records_who_did_it(db_session):
    loja = _loja(db_session, areas="Valinhos,  campinas\nValinhos ; Vinhedo ", pool_types=["fibra", "vinil"])

    from piscinow.matching.service import get_profile
    profile = get_profile(db_session, loja.id)
    assert profile.service_areas == ["Valinhos", "campinas", "Vinhedo"]
    assert profile.pool_types == ["fibra", "vinil"]
    assert profile.updated_by == "admin:equipe@piscinow.com.br"


def test_saving_the_profile_again_updates_it_instead_of_duplicating(db_session):
    loja = _loja(db_session)

    save_profile(db_session, loja, areas="Jundiaí", pool_types=["vinil"], budget_bands=[], capacity=5, active=False, actor="admin:x")

    from piscinow.matching.service import get_profile
    profile = get_profile(db_session, loja.id)
    assert (profile.service_areas, profile.capacity, profile.active) == (["Jundiaí"], 5, False)


@pytest.mark.parametrize("args", [
    dict(pool_types=["cristal"]),
    dict(budget_bands=["gratis"]),
    dict(capacity=0),
    dict(areas="  ,  "),
])
def test_an_invalid_profile_is_rejected(db_session, args):
    with pytest.raises(ProfileError):
        _loja(db_session, **args)


def test_running_the_matching_evaluates_every_approved_store_and_records_the_reasons(db_session):
    deal = _deal(db_session)
    fits = _loja(db_session, "Studio Fibra Sul")
    wrong_city = _loja(db_session, "Vinil & Cia", areas="Sorocaba")
    no_profile = _loja(db_session, "Sem Perfil", profile=False)
    not_approved = _loja(db_session, "Pendente", approved=False)

    summary = run_matching(db_session, deal, actor="admin:equipe@piscinow.com.br")

    decisions = _decisions(db_session, deal)
    assert set(decisions) == {fits.id, wrong_city.id, no_profile.id}
    assert not_approved.id not in decisions
    assert decisions[fits.id].eligible is True
    assert decisions[wrong_city.id].eligible is False
    assert next(c for c in decisions[wrong_city.id].criteria if c["key"] == "cidade")["detail"] == "Não atende Valinhos"
    assert (summary.evaluated, summary.eligible) == (3, 1)
    assert deal.status == DealStatus.MATCHED
    event = db_session.query(DealEvent).filter_by(deal_id=deal.id, kind="matching_run").one()
    assert "1 elegível" in event.note and "3 avaliadas" in event.note


def test_running_the_matching_again_keeps_the_overrides(db_session):
    deal = _deal(db_session)
    wrong_city = _loja(db_session, "Vinil & Cia", areas="Sorocaba")
    run_matching(db_session, deal, actor="admin:x")
    decision = _decisions(db_session, deal)[wrong_city.id]
    set_override(db_session, decision, MatchOverride.INCLUIDA, reason="Atende a região por parceria", actor="admin:x")

    run_matching(db_session, deal, actor="admin:x")

    decision = _decisions(db_session, deal)[wrong_city.id]
    assert decision.eligible is False
    assert decision.override == MatchOverride.INCLUIDA
    assert db_session.query(MatchingDecision).filter_by(deal_id=deal.id).count() == 1


def test_an_override_needs_a_reason_and_is_recorded(db_session):
    deal = _deal(db_session)
    loja = _loja(db_session)
    run_matching(db_session, deal, actor="admin:x")
    decision = _decisions(db_session, deal)[loja.id]

    with pytest.raises(ValueError):
        set_override(db_session, decision, MatchOverride.EXCLUIDA, reason=" ", actor="admin:x")
    assert decision.override == MatchOverride.NENHUM

    set_override(db_session, decision, MatchOverride.EXCLUIDA, reason="Loja em férias coletivas", actor="admin:equipe")

    assert decision.override == MatchOverride.EXCLUIDA
    assert (decision.override_reason, decision.override_by) == ("Loja em férias coletivas", "admin:equipe")
    assert decision.override_at is not None
    assert decision.eligible is True  # the original system result is never overwritten


def test_clearing_an_override_needs_no_reason(db_session):
    deal = _deal(db_session)
    loja = _loja(db_session)
    run_matching(db_session, deal, actor="admin:x")
    decision = _decisions(db_session, deal)[loja.id]
    set_override(db_session, decision, MatchOverride.EXCLUIDA, reason="Férias", actor="admin:x")

    set_override(db_session, decision, MatchOverride.NENHUM, reason="", actor="admin:x")

    assert decision.override == MatchOverride.NENHUM


def test_sharing_marks_only_the_effective_stores_and_moves_the_deal_forward(db_session):
    deal = _deal(db_session)
    fits = _loja(db_session, "Studio Fibra Sul")
    excluded = _loja(db_session, "Excluída", areas="Valinhos")
    wrong = _loja(db_session, "Longe", areas="Sorocaba")
    run_matching(db_session, deal, actor="admin:x")
    decisions = _decisions(db_session, deal)
    set_override(db_session, decisions[excluded.id], MatchOverride.EXCLUIDA, reason="Sem estoque", actor="admin:x")

    count = share_with_partners(db_session, deal, actor="admin:x")

    decisions = _decisions(db_session, deal)
    assert count == 1
    assert decisions[fits.id].shared_at is not None
    assert decisions[excluded.id].shared_at is None
    assert decisions[wrong.id].shared_at is None
    assert deal.status == DealStatus.PARTNER_REVIEW


def test_sharing_without_any_effective_store_is_refused(db_session):
    deal = _deal(db_session)
    _loja(db_session, areas="Sorocaba")
    run_matching(db_session, deal, actor="admin:x")

    with pytest.raises(ValueError):
        share_with_partners(db_session, deal, actor="admin:x")
    assert deal.status == DealStatus.MATCHED


def test_after_sharing_the_matching_and_overrides_are_frozen(db_session):
    deal = _deal(db_session)
    loja = _loja(db_session)
    run_matching(db_session, deal, actor="admin:x")
    share_with_partners(db_session, deal, actor="admin:x")

    with pytest.raises(ValueError):
        run_matching(db_session, deal, actor="admin:x")
    with pytest.raises(ValueError):
        set_override(db_session, _decisions(db_session, deal)[loja.id], MatchOverride.EXCLUIDA, reason="x", actor="admin:x")


def test_a_store_at_capacity_with_shared_deals_is_ineligible_for_the_next_one(db_session):
    loja = _loja(db_session, capacity=1)
    first = _deal(db_session, "Primeira")
    run_matching(db_session, first, actor="admin:x")
    share_with_partners(db_session, first, actor="admin:x")
    assert open_load(db_session, loja.id) == 1

    second = _deal(db_session, "Segunda")
    run_matching(db_session, second, actor="admin:x")

    decision = _decisions(db_session, second)[loja.id]
    assert decision.eligible is False
    assert next(c for c in decision.criteria if c["key"] == "capacidade")["passed"] is False
