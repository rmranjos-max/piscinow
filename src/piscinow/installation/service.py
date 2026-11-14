from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.matching.rules import city_matches
from piscinow.matching.service import MAX_AREA_LENGTH, MAX_AREAS, parse_areas
from piscinow.models.installation import AssignmentStatus, InstallerAssignment, InstallerProfile
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.proposal import Proposal, ProposalStatus
from piscinow.models.qualification import Deal, DealStatus, LeadQualification
from piscinow.models.service import ServiceKind
from piscinow.qualification.deals import record_event
from piscinow.qualification.projection import partner_briefing

SERVICE_KINDS = {
    ServiceKind.INSTALACAO.value: "Instalação",
    ServiceKind.MANUTENCAO.value: "Manutenção",
    ServiceKind.REPARO.value: "Reparo",
}
LIVE = (AssignmentStatus.PENDENTE, AssignmentStatus.ACEITA)


class InstallationError(Exception):
    def __init__(self, *errors: str):
        super().__init__(errors[0] if errors else "")
        self.errors = list(errors)


def get_installer_profile(db: Session, member_id) -> InstallerProfile | None:
    return db.scalar(select(InstallerProfile).where(InstallerProfile.member_id == member_id))


def save_installer_profile(
    db: Session, member: Member, *, areas: str, service_kinds: list[str], active: bool, actor: str
) -> InstallerProfile:
    cities = parse_areas(areas)
    if not cities:
        raise InstallationError("Informe ao menos uma cidade atendida.")
    if len(cities) > MAX_AREAS or any(len(city) > MAX_AREA_LENGTH for city in cities):
        raise InstallationError("Lista de cidades longa demais.")
    if not service_kinds:
        raise InstallationError("Marque ao menos um tipo de serviço.")
    if any(kind not in SERVICE_KINDS for kind in service_kinds):
        raise InstallationError("Tipo de serviço inválido.")

    profile = get_installer_profile(db, member.id)
    if profile is None:
        profile = InstallerProfile(member_id=member.id)
        db.add(profile)
    profile.service_areas = cities
    profile.service_kinds = list(dict.fromkeys(service_kinds))
    profile.active = active
    profile.updated_by = actor
    profile.updated_at = datetime.now(timezone.utc)
    db.flush()
    return profile


def _location(db: Session, deal: Deal) -> str:
    return db.get(LeadQualification, deal.qualification_id).values().get("localizacao", "")


def candidate_installers(db: Session, deal: Deal) -> list[dict]:
    """Approved installers with a hint about the buyer's city. Only a hint: the team decides."""
    location = _location(db, deal)
    candidates = []
    for member in db.scalars(
        select(Member).where(Member.profile_type == ProfileType.PRESTADOR, Member.status == MemberStatus.APPROVED)
        .order_by(Member.name)
    ):
        profile = get_installer_profile(db, member.id)
        if profile is None:
            serves, note = False, "Sem perfil de atendimento"
        elif not profile.active:
            serves, note = False, "Perfil inativo"
        else:
            area = city_matches(list(profile.service_areas), location)
            serves, note = (True, f"Atende {area}") if area else (False, f"Não atende {location or 'a cidade do comprador'}")
        candidates.append({"member": member, "serves": serves, "note": note})
    candidates.sort(key=lambda c: (not c["serves"], c["member"].name))
    return candidates


def live_assignment(db: Session, deal: Deal) -> InstallerAssignment | None:
    return db.scalar(select(InstallerAssignment).where(
        InstallerAssignment.deal_id == deal.id, InstallerAssignment.status.in_(LIVE)
    ))


def assign_installer(db: Session, deal: Deal, installer: Member, *, reason: str, actor: str) -> InstallerAssignment:
    if deal.status != DealStatus.ACCEPTED:
        raise InstallationError("Só é possível atribuir um instalador a uma oportunidade com proposta aceita.")
    if installer.profile_type != ProfileType.PRESTADOR or installer.status != MemberStatus.APPROVED:
        raise InstallationError("Escolha um instalador aprovado.")
    reason = (reason or "").strip()
    if not reason:
        raise InstallationError("Informe o motivo da atribuição.")

    now = datetime.now(timezone.utc)
    previous = live_assignment(db, deal)
    if previous is not None:
        previous.status = AssignmentStatus.CANCELADA
        previous.cancel_reason = f"Reatribuída: {reason[:400]}"
        previous.cancelled_at = now
        db.flush()

    assignment = InstallerAssignment(
        deal_id=deal.id, installer_member_id=installer.id, assigned_reason=reason[:500], assigned_by=actor, assigned_at=now,
    )
    db.add(assignment)
    db.flush()
    record_event(db, deal, "installer_assigned", actor=actor, note=f"{installer.name}: {reason[:200]}")
    return assignment


def respond_assignment(
    db: Session, assignment: InstallerAssignment, installer: Member, *, answer: str, reason: str
) -> None:
    if assignment.installer_member_id != installer.id:
        raise InstallationError("Esta atribuição não está disponível.")
    if assignment.status != AssignmentStatus.PENDENTE:
        raise InstallationError("Esta atribuição já foi respondida.")
    if answer not in ("aceita", "recusada"):
        raise InstallationError("Resposta inválida.")
    reason = (reason or "").strip()
    if answer == "recusada" and not reason:
        raise InstallationError("Informe o motivo para recusar.")

    assignment.status = AssignmentStatus(answer)
    assignment.response_reason = reason[:500] if answer == "recusada" else None
    assignment.responded_at = datetime.now(timezone.utc)
    deal = db.get(Deal, assignment.deal_id)
    label = "aceitou a instalação" if answer == "aceita" else f"recusou a instalação ({assignment.response_reason})"
    record_event(db, deal, "installer_response", actor=f"prestador:{installer.id}", note=f"{installer.name} {label}")


def responsible_installer(db: Session, deal: Deal) -> Member | None:
    """The installer the buyer may see: only one who accepted the job."""
    assignment = db.scalar(select(InstallerAssignment).where(
        InstallerAssignment.deal_id == deal.id, InstallerAssignment.status == AssignmentStatus.ACEITA
    ))
    return db.get(Member, assignment.installer_member_id) if assignment else None


def inbox_for_installer(db: Session, installer_id) -> list[dict]:
    rows = db.execute(
        select(InstallerAssignment, Deal)
        .join(Deal, InstallerAssignment.deal_id == Deal.id)
        .where(
            InstallerAssignment.installer_member_id == installer_id,
            InstallerAssignment.status != AssignmentStatus.CANCELADA,
            Deal.status == DealStatus.ACCEPTED,
        )
        .order_by(InstallerAssignment.assigned_at.desc())
    )
    items = []
    for assignment, deal in rows:
        proposal = db.scalar(select(Proposal).where(Proposal.deal_id == deal.id, Proposal.status == ProposalStatus.ACEITA))
        store = db.get(Member, deal.assigned_member_id) if deal.assigned_member_id else None
        buyer = db.get(Member, deal.member_id)
        qualification = db.get(LeadQualification, deal.qualification_id)
        accepted = assignment.status == AssignmentStatus.ACEITA
        items.append({
            "assignment": assignment,
            # Catalog fields only. The price of the store's proposal is deliberately left out.
            "briefing": partner_briefing(deal.member_id, qualification.values()),
            "store": store.name if store else None,
            "scope": proposal.scope if proposal else None,
            "exclusions": proposal.exclusions if proposal else None,
            "lead_time_days": proposal.lead_time_days if proposal else None,
            "contact": (
                {"nome": buyer.name, "email": buyer.email, "telefone": buyer.phone, "regiao": buyer.region} if accepted else None
            ),
        })
    return items
