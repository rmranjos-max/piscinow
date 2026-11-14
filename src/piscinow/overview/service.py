from sqlalchemy import func, select
from sqlalchemy.orm import Session

from piscinow.models.installation import AssignmentStatus, InstallerAssignment
from piscinow.models.member import Member, MemberStatus
from piscinow.models.qualification import ConsentState, Deal, DealEvent, DealStatus, LeadQualification
from piscinow.overview.stats import average_duration, format_duration, funnel, loss_reasons

# Event kinds shown in the governance trail, grouped the way the team looks for them.
EVENT_KINDS = {
    "created": "Oportunidade criada",
    "status_changed": "Mudança de estado",
    "matching_run": "Matching executado",
    "matching_override": "Revisão do matching",
    "shared": "Encaminhada às lojas",
    "partner_response": "Resposta da loja",
    "proposal_sent": "Proposta enviada",
    "revision_requested": "Revisão pedida",
    "proposal_rejected": "Proposta recusada",
    "proposal_accepted": "Proposta aceita",
    "contact_released": "Contato liberado",
    "feasibility": "Viabilidade",
    "installer_assigned": "Instalador atribuído",
    "installer_response": "Resposta do instalador",
}
EVENT_GROUPS = {
    "todas": ("Todas", None),
    "matching": ("Matching", ("matching_run", "matching_override", "shared", "partner_response")),
    "propostas": ("Propostas", ("proposal_sent", "revision_requested", "proposal_rejected", "proposal_accepted")),
    "contato": ("Contato liberado", ("contact_released",)),
    "viabilidade": ("Viabilidade", ("feasibility",)),
    "instalacao": ("Instalação", ("installer_assigned", "installer_response")),
    "estado": ("Estados e perdas", ("created", "status_changed")),
}
PAGE_SIZE = 50


def gather_overview(db: Session) -> dict:
    """Numbers for the admin overview. Everything comes from the database; nothing is made up."""
    counts = {
        status.value: count
        for status, count in db.execute(select(Deal.status, func.count()).group_by(Deal.status))
    }
    reasons = list(db.scalars(select(Deal.lost_reason).where(Deal.status == DealStatus.LOST)))

    accepted_at = {
        deal_id: when for deal_id, when in db.execute(
            select(DealEvent.deal_id, func.min(DealEvent.created_at)).where(DealEvent.kind == "proposal_accepted")
            .group_by(DealEvent.deal_id)
        )
    }
    created_at = {deal_id: when for deal_id, when in db.execute(select(Deal.id, Deal.created_at))}
    durations = [(created_at[deal_id], when) for deal_id, when in accepted_at.items() if deal_id in created_at]

    live = {
        deal_id: status for deal_id, status in db.execute(
            select(InstallerAssignment.deal_id, InstallerAssignment.status).where(
                InstallerAssignment.status.in_((AssignmentStatus.PENDENTE, AssignmentStatus.ACEITA))
            )
        )
    }
    accepted_deals = list(db.scalars(select(Deal.id).where(Deal.status == DealStatus.ACCEPTED)))

    return {
        "funnel": funnel(counts),
        "deals_total": sum(counts.values()),
        "loss_reasons": loss_reasons(reasons),
        "avg_to_accept": format_duration(average_duration(durations)),
        "qualifications_total": db.scalar(select(func.count()).select_from(LeadQualification)),
        "consent_granted": db.scalar(
            select(func.count()).select_from(LeadQualification).where(LeadQualification.consent == ConsentState.CONCEDIDO)
        ),
        "attention_open": db.scalar(
            select(func.count()).select_from(LeadQualification).where(LeadQualification.attention_at.is_not(None))
        ),
        "waitlist": db.scalar(select(func.count()).select_from(Member).where(Member.status == MemberStatus.WAITLISTED)),
        "accepted_without_installer": sum(1 for deal_id in accepted_deals if deal_id not in live),
        "installer_pending": sum(1 for deal_id in accepted_deals if live.get(deal_id) == AssignmentStatus.PENDENTE),
    }


def governance_page(db: Session, group: str, page: int) -> dict:
    if group not in EVENT_GROUPS:
        group = "todas"
    kinds = EVENT_GROUPS[group][1]
    query = (
        select(DealEvent, Deal, LeadQualification)
        .join(Deal, DealEvent.deal_id == Deal.id)
        .join(LeadQualification, Deal.qualification_id == LeadQualification.id)
    )
    total_query = select(func.count()).select_from(DealEvent)
    if kinds:
        query = query.where(DealEvent.kind.in_(kinds))
        total_query = total_query.where(DealEvent.kind.in_(kinds))
    total = db.scalar(total_query)
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(page, 1), pages)
    rows = db.execute(
        query.order_by(DealEvent.created_at.desc(), DealEvent.id).limit(PAGE_SIZE).offset((page - 1) * PAGE_SIZE)
    )
    return {
        "group": group, "page": page, "pages": pages, "total": total,
        "events": [
            {"event": event, "code": deal.code, "qualification_id": qualification.id,
             "kind_label": EVENT_KINDS.get(event.kind, event.kind)}
            for event, deal, qualification in rows
        ],
    }
