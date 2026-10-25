from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.conversation import Conversation, Message, MessageRole
from piscinow.models.member import Member
from piscinow.models.qualification import (
    ConsentState,
    FieldSource,
    LeadQualification,
    QualificationField,
    QualificationStatus,
    Verification,
)
from piscinow.qualification.deals import cancel_for_withdrawn_consent, open_deal_if_qualified
from piscinow.qualification.fields import FIELDS, normalize_field
from piscinow.qualification.flow import is_qualified

PURPOSE = "qualificacao"


def greeting(first_name: str) -> str:
    who = f"Oi, {first_name}!" if first_name else "Oi!"
    return (
        f"{who} Eu sou a assistente virtual da Piscinow. Estou aqui para entender o que você "
        "imagina para a sua piscina e preparar tudo para as lojas do Clube te atenderem bem. "
        "Para começar: em que cidade fica o terreno?"
    )


def find_qualification(db: Session, member: Member) -> LeadQualification | None:
    return db.scalar(select(LeadQualification).where(LeadQualification.member_id == member.id))


def get_or_create_qualification(db: Session, member: Member) -> LeadQualification:
    """The buyer's single qualification and its conversation; created with the opening message."""
    qualification = find_qualification(db, member)
    if qualification is not None:
        return qualification
    conversation = Conversation(member_id=member.id, purpose=PURPOSE)
    db.add(conversation)
    db.flush()
    first_name = (member.name or "").split()[0] if (member.name or "").strip() else ""
    db.add(Message(conversation=conversation, role=MessageRole.AGENT, content=greeting(first_name)))
    # The greeting already asked for the location, which counts as the first ask.
    qualification = LeadQualification(member_id=member.id, conversation_id=conversation.id, asks={"localizacao": 1})
    db.add(qualification)
    db.flush()
    return qualification


def conversation_of(db: Session, qualification: LeadQualification) -> Conversation:
    return db.get(Conversation, qualification.conversation_id)


def set_field(
    db: Session,
    qualification: LeadQualification,
    key: str,
    raw_value,
    *,
    source: FieldSource,
    actor: str,
    verification: Verification = Verification.DECLARADO,
) -> bool:
    """Validate and store one field. Returns False (and stores nothing) when the value is invalid."""
    value = normalize_field(key, raw_value)
    if value is None:
        return False
    existing = next((f for f in qualification.fields if f.key == key), None)
    if existing is None:
        field = QualificationField(
            qualification_id=qualification.id, key=key, value=value,
            source=source, verification=verification, updated_by=actor,
        )
        db.add(field)
        qualification.fields.append(field)
    elif existing.value != value or existing.source != source:
        existing.value = value
        existing.source = source
        existing.verification = verification
        existing.updated_by = actor
        existing.updated_at = datetime.now(timezone.utc)
    db.flush()
    return True


def count_ask(qualification: LeadQualification, key: str) -> None:
    # JSONB columns only notice a reassignment, never an in-place change.
    asks = dict(qualification.asks or {})
    asks[key] = asks.get(key, 0) + 1
    qualification.asks = asks


def request_attention(qualification: LeadQualification, note: str) -> None:
    """Flag the buyer for the team. The first reason is kept; later ones are appended."""
    note = note.strip()[:300]
    if not note:
        return
    if qualification.attention_note and note not in qualification.attention_note:
        qualification.attention_note = f"{qualification.attention_note}\n{note}"[:1000]
    elif not qualification.attention_note:
        qualification.attention_note = note
    qualification.attention_at = qualification.attention_at or datetime.now(timezone.utc)


def set_consent(db: Session, qualification: LeadQualification, granted: bool) -> None:
    qualification.consent = ConsentState.CONCEDIDO if granted else ConsentState.RECUSADO
    qualification.consent_at = datetime.now(timezone.utc)
    if not granted:
        cancel_for_withdrawn_consent(db, qualification)
    refresh_status(db, qualification)


def refresh_status(db: Session, qualification: LeadQualification) -> None:
    values = qualification.values()
    if is_qualified(values, qualification.consent.value):
        qualification.status = QualificationStatus.QUALIFICADA
    else:
        qualification.status = QualificationStatus.EM_ANDAMENTO
    db.flush()
    open_deal_if_qualified(db, qualification)


def known_fields(qualification: LeadQualification) -> list[dict]:
    """The buyer's own view of the briefing, in catalog order, with where each value came from."""
    by_key = {field.key: field for field in qualification.fields}
    rows = []
    for key, definition in FIELDS.items():
        field = by_key.get(key)
        rows.append({
            "key": key,
            "label": definition.label,
            "required": definition.required,
            "choices": definition.choices,
            "value": field.value if field else None,
            "source": field.source.value if field else None,
            "verification": field.verification.value if field else None,
        })
    return rows
