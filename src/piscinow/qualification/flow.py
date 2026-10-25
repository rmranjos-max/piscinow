from dataclasses import dataclass

from piscinow.qualification.fields import REQUIRED

# After this many unanswered asks of a required field, hand the conversation to the team.
MAX_REQUIRED_ASKS = 3
# Optional fields are asked at most this many times (the budget twice, by business decision).
OPTIONAL_MAX_ASKS = {"dimensoes": 1, "orcamento": 2, "terreno": 1}
OPTIONAL_ORDER = ("dimensoes", "orcamento", "terreno")


@dataclass(frozen=True)
class Goal:
    """What the next reply should try to achieve. Decided by code, never by the model."""

    kind: str  # ask_field | ask_budget | ask_consent | handoff | complete
    field: str | None = None
    attempt: int | None = None


def next_goal(values: dict, asks: dict, consent: str) -> Goal:
    for key in REQUIRED:
        if key not in values:
            if asks.get(key, 0) >= MAX_REQUIRED_ASKS:
                return Goal("handoff", key)
            return Goal("ask_field", key, asks.get(key, 0) + 1)
    for key in OPTIONAL_ORDER:
        if key not in values and asks.get(key, 0) < OPTIONAL_MAX_ASKS[key]:
            kind = "ask_budget" if key == "orcamento" else "ask_field"
            return Goal(kind, key, asks.get(key, 0) + 1)
    if consent == "nao_respondido":
        return Goal("ask_consent")
    return Goal("complete")


def resolve_budget(values: dict, asks: dict) -> str | None:
    """After two unanswered budget asks the budget is recorded as not informed."""
    if "orcamento" not in values and asks.get("orcamento", 0) >= OPTIONAL_MAX_ASKS["orcamento"]:
        return "nao_informado"
    return None


def is_qualified(values: dict, consent: str) -> bool:
    return consent == "concedido" and all(key in values for key in REQUIRED)
