from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

MAX_AMOUNT = Decimal("99999999.99")
MAX_LEAD_TIME_DAYS = 730
MAX_VALIDITY_DAYS = 180

FEASIBILITY_ITEMS = {
    "acesso": "Acesso ao imóvel",
    "terreno": "Terreno",
    "escavacao": "Escavação",
    "hidraulica_eletrica": "Instalações hidráulicas e elétricas",
    "medidas": "Medidas",
    "visita": "Necessidade de visita técnica",
}
ITEM_STATES = ("pendente", "ok", "ressalva", "impeditivo")
FEASIBILITY_STATUSES = ("pending", "conditionally_approved", "approved", "rejected")


def parse_amount(raw) -> Decimal | None:
    """A monetary value typed by a person, pt-BR style, or None.

    One separator at most ("18000,50" or "18000.50"); a grouped "18.000,50" is rejected instead of
    guessed at, and so is "18.000" (three decimals), which would silently become R$ 18,00.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or sum(text.count(c) for c in ".,") > 1:
        return None
    try:
        amount = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2 or amount > MAX_AMOUNT:
        return None
    if "e" in text.lower():
        return None
    return amount


def total_of(amounts) -> Decimal:
    return sum(amounts, Decimal("0"))


def validate_proposal(
    *, items: list[tuple[str, Decimal]], scope: str, lead_time_days: int, valid_until: date, today: date
) -> list[str]:
    errors = []
    if not items:
        errors.append("Inclua ao menos um item na proposta.")
    if any(not (description or "").strip() for description, _ in items):
        errors.append("Todo item precisa de uma descrição.")
    if any(amount is None or amount <= 0 for _, amount in items):
        errors.append("Todo item precisa de um valor positivo.")
    elif total_of(amount for _, amount in items) > MAX_AMOUNT:
        errors.append("O total da proposta excede o limite permitido.")
    if not (scope or "").strip():
        errors.append("Descreva o escopo da proposta.")
    if not 1 <= lead_time_days <= MAX_LEAD_TIME_DAYS:
        errors.append(f"Informe um prazo estimado entre 1 e {MAX_LEAD_TIME_DAYS} dias.")
    if valid_until <= today:
        errors.append("A validade deve ser uma data futura.")
    elif valid_until > today + timedelta(days=MAX_VALIDITY_DAYS):
        errors.append(f"A validade deve ser de no máximo {MAX_VALIDITY_DAYS} dias.")
    return errors


def is_expired(valid_until: date, today: date) -> bool:
    """Valid through its last day."""
    return today > valid_until


def validate_feasibility(status: str, items: list[dict], notes: str) -> list[str]:
    if status not in FEASIBILITY_STATUSES:
        return ["Resultado de viabilidade inválido."]
    keys = [item.get("key") for item in items]
    if sorted(keys) != sorted(FEASIBILITY_ITEMS) or any(item.get("state") not in ITEM_STATES for item in items):
        return ["O checklist de viabilidade está incompleto ou inválido."]
    states = {item["state"] for item in items}
    if status == "approved" and states != {"ok"}:
        return ["Para aprovar, todos os itens precisam estar ok."]
    if status == "conditionally_approved" and states & {"pendente", "impeditivo"}:
        return ["Aprovação com ressalvas não admite item pendente ou impeditivo."]
    if status == "rejected" and not (notes or "").strip():
        return ["Explique o motivo da reprovação."]
    return []


def acceptance_blocker(status: str | None) -> str | None:
    """Why the buyer cannot accept yet, or None when the viability allows it."""
    if status in ("approved", "conditionally_approved"):
        return None
    if status == "rejected":
        return "A viabilidade do projeto foi reprovada pela equipe; não é possível aceitar."
    if status == "pending":
        return "A viabilidade do projeto está pendente; a equipe precisa concluir a avaliação antes do aceite."
    return "A viabilidade do projeto ainda não foi avaliada pela equipe."


def caveats(items: list[dict]) -> list[dict]:
    return [
        {"label": FEASIBILITY_ITEMS[item["key"]], "note": item.get("note", "")}
        for item in items if item.get("state") == "ressalva"
    ]
