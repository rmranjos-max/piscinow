import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.matching.rules import StoreProfile, evaluate, is_effective
from piscinow.models.matching import MatchingDecision, MatchOverride, PartnerProfile
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import Deal, DealStatus, LeadQualification
from piscinow.qualification.deals import CLOSED, record_event
from piscinow.qualification.fields import FIELDS

POOL_TYPES = {k: v for k, v in FIELDS["tipo_piscina"].choices.items() if k != "ainda_nao_sei"}
BUDGET_BANDS = {k: v for k, v in FIELDS["orcamento"].choices.items() if k != "nao_informado"}
MAX_AREAS = 50
MAX_AREA_LENGTH = 80
EDITABLE = (DealStatus.QUALIFIED, DealStatus.MATCHED)


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class MatchSummary:
    evaluated: int
    eligible: int


def get_profile(db: Session, member_id) -> PartnerProfile | None:
    return db.scalar(select(PartnerProfile).where(PartnerProfile.member_id == member_id))


def parse_areas(raw: str) -> list[str]:
    seen, areas = set(), []
    for piece in re.split(r"[,;\n]", raw or ""):
        name = re.sub(r"\s+", " ", piece).strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            areas.append(name)
    return areas


def save_profile(
    db: Session, member: Member, *, areas: str, pool_types: list[str], budget_bands: list[str],
    capacity: int, active: bool, actor: str,
) -> PartnerProfile:
    cities = parse_areas(areas)
    if not cities:
        raise ProfileError("Informe ao menos uma cidade atendida.")
    if len(cities) > MAX_AREAS or any(len(city) > MAX_AREA_LENGTH for city in cities):
        raise ProfileError("Lista de cidades longa demais.")
    if any(kind not in POOL_TYPES for kind in pool_types):
        raise ProfileError("Tipo de piscina inválido.")
    if any(band not in BUDGET_BANDS for band in budget_bands):
        raise ProfileError("Faixa de orçamento inválida.")
    if capacity < 1:
        raise ProfileError("A capacidade deve ser de pelo menos 1.")

    profile = get_profile(db, member.id)
    if profile is None:
        profile = PartnerProfile(member_id=member.id)
        db.add(profile)
    profile.service_areas = cities
    profile.pool_types = list(dict.fromkeys(pool_types))
    profile.budget_bands = list(dict.fromkeys(budget_bands))
    profile.capacity = capacity
    profile.active = active
    profile.updated_by = actor
    profile.updated_at = datetime.now(timezone.utc)
    db.flush()
    return profile


def _active_shared(db: Session, partner_id):
    """Decisions the store is working on: shared, effective, not declined, deal still alive."""
    rows = db.execute(
        select(MatchingDecision, Deal)
        .join(Deal, MatchingDecision.deal_id == Deal.id)
        .where(MatchingDecision.partner_member_id == partner_id, MatchingDecision.shared_at.is_not(None))
    )
    return [
        decision for decision, deal in rows
        if deal.status not in CLOSED
        and not (deal.status == DealStatus.ACCEPTED and deal.assigned_member_id != partner_id)
        and decision.response.value != "recusada"
        and is_effective(decision.eligible, decision.override.value)
    ]


def open_load(db: Session, partner_id) -> int:
    return len(_active_shared(db, partner_id))


def _decisions_of(db: Session, deal: Deal) -> list[MatchingDecision]:
    return list(db.scalars(select(MatchingDecision).where(MatchingDecision.deal_id == deal.id)))


def run_matching(db: Session, deal: Deal, *, actor: str) -> MatchSummary:
    if deal.status not in EDITABLE:
        raise ValueError("O matching só pode ser executado antes do encaminhamento às lojas.")
    values = _values_of(db, deal)
    existing = {d.partner_member_id: d for d in _decisions_of(db, deal)}
    stores = list(db.scalars(
        select(Member).where(Member.profile_type == ProfileType.LOJA, Member.status == MemberStatus.APPROVED)
        .order_by(Member.name)
    ))

    eligible = 0
    for store in stores:
        profile = get_profile(db, store.id)
        stored = (
            StoreProfile(
                active=profile.active, service_areas=list(profile.service_areas), pool_types=list(profile.pool_types),
                budget_bands=list(profile.budget_bands), capacity=profile.capacity,
            ) if profile else None
        )
        result = evaluate(stored, approved=True, values=values, open_load=open_load(db, store.id))
        decision = existing.get(store.id)
        if decision is None:
            decision = MatchingDecision(deal_id=deal.id, partner_member_id=store.id, eligible=result.eligible)
            db.add(decision)
        decision.eligible = result.eligible
        decision.criteria = result.criteria
        eligible += result.eligible
    db.flush()

    previous = deal.status
    deal.status = DealStatus.MATCHED
    record_event(
        db, deal, "matching_run", actor=actor, from_status=previous.value, to_status=DealStatus.MATCHED.value,
        note=f"{eligible} elegível(is) de {len(stores)} avaliadas",
    )
    return MatchSummary(evaluated=len(stores), eligible=eligible)


def _values_of(db: Session, deal: Deal) -> dict:
    return db.get(LeadQualification, deal.qualification_id).values()


def set_override(
    db: Session, decision: MatchingDecision, override: MatchOverride, *, reason: str, actor: str
) -> None:
    deal = db.get(Deal, decision.deal_id)
    if deal.status not in EDITABLE:
        raise ValueError("A revisão só é possível antes do encaminhamento às lojas.")
    reason = (reason or "").strip()
    if override != MatchOverride.NENHUM and not reason:
        raise ValueError("O motivo é obrigatório para incluir ou excluir uma loja.")
    decision.override = override
    decision.override_reason = reason[:500] if override != MatchOverride.NENHUM else None
    decision.override_by = actor if override != MatchOverride.NENHUM else None
    decision.override_at = datetime.now(timezone.utc) if override != MatchOverride.NENHUM else None
    store = db.get(Member, decision.partner_member_id)
    record_event(
        db, deal, "matching_override", actor=actor,
        note=f"{store.name}: {override.value}" + (f" ({reason[:200]})" if reason and override != MatchOverride.NENHUM else ""),
    )


def effective_decisions(db: Session, deal: Deal) -> list[MatchingDecision]:
    return [d for d in _decisions_of(db, deal) if is_effective(d.eligible, d.override.value)]


def share_with_partners(db: Session, deal: Deal, *, actor: str) -> int:
    if deal.status != DealStatus.MATCHED:
        raise ValueError("Execute o matching antes de encaminhar às lojas.")
    chosen = effective_decisions(db, deal)
    if not chosen:
        raise ValueError("Nenhuma loja elegível para receber o briefing.")
    now = datetime.now(timezone.utc)
    for decision in chosen:
        decision.shared_at = now
    previous = deal.status
    deal.status = DealStatus.PARTNER_REVIEW
    record_event(
        db, deal, "shared", actor=actor, from_status=previous.value, to_status=DealStatus.PARTNER_REVIEW.value,
        note=f"Briefing encaminhado a {len(chosen)} loja(s)",
    )
    return len(chosen)
