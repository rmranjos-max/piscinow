import re
import unicodedata
from dataclasses import dataclass

from piscinow.qualification.fields import label_for


@dataclass(frozen=True)
class StoreProfile:
    active: bool
    service_areas: list[str]
    pool_types: list[str]
    budget_bands: list[str]
    capacity: int


@dataclass(frozen=True)
class MatchResult:
    eligible: bool
    criteria: list[dict]


CRITERIA = (
    ("homologada", "Loja aprovada no Clube"),
    ("perfil", "Perfil de atendimento ativo"),
    ("cidade", "Cidade atendida"),
    ("tipo", "Tipo de piscina"),
    ("orcamento", "Faixa de orçamento"),
    ("capacidade", "Capacidade livre"),
)
_LABELS = dict(CRITERIA)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", stripped).strip()


def city_matches(service_areas: list[str], location: str | None) -> str | None:
    """The served city that appears as a whole word in the buyer's location, or None."""
    if not location:
        return None
    haystack = _fold(location)
    for area in service_areas:
        needle = _fold(area)
        if needle and re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack):
            return area
    return None


def _check(key: str, passed: bool, detail: str) -> dict:
    return {"key": key, "label": _LABELS[key], "passed": passed, "detail": detail}


def evaluate(profile: StoreProfile | None, *, approved: bool, values: dict, open_load: int) -> MatchResult:
    """Deterministic eligibility of one store for one briefing. Every criterion is recorded."""
    criteria = [_check("homologada", approved, "Aprovada" if approved else "Loja não aprovada no Clube")]

    if profile is None or not profile.active:
        reason = "Sem perfil de atendimento" if profile is None else "Perfil de atendimento inativo"
        criteria.append(_check("perfil", False, reason))
        criteria += [
            _check(key, False, f"Não avaliado: {reason.lower()}") for key in ("cidade", "tipo", "orcamento", "capacidade")
        ]
        return MatchResult(False, criteria)

    criteria.append(_check("perfil", True, "Perfil ativo"))

    location = values.get("localizacao")
    area = city_matches(profile.service_areas, location)
    if area:
        criteria.append(_check("cidade", True, f"Atende {area}"))
    elif location:
        criteria.append(_check("cidade", False, f"Não atende {location}"))
    else:
        criteria.append(_check("cidade", False, "Comprador não informou a localização"))

    pool = values.get("tipo_piscina")
    if pool in (None, "ainda_nao_sei"):
        criteria.append(_check("tipo", True, "Comprador ainda não sabe o tipo de piscina"))
    elif pool in profile.pool_types:
        criteria.append(_check("tipo", True, f"Trabalha com {label_for('tipo_piscina', pool).lower()}"))
    else:
        criteria.append(_check("tipo", False, f"Não trabalha com {label_for('tipo_piscina', pool).lower()}"))

    budget = values.get("orcamento")
    if budget in (None, "nao_informado"):
        criteria.append(_check("orcamento", True, "Orçamento não informado pelo comprador"))
    elif budget in profile.budget_bands:
        criteria.append(_check("orcamento", True, f"Atende a faixa {label_for('orcamento', budget)}"))
    else:
        criteria.append(_check("orcamento", False, f"Não atende a faixa {label_for('orcamento', budget)}"))

    criteria.append(_check(
        "capacidade", profile.capacity - open_load > 0,
        f"{open_load} de {profile.capacity} oportunidades em andamento",
    ))
    return MatchResult(all(c["passed"] for c in criteria), criteria)


def is_effective(eligible: bool, override: str) -> bool:
    """Whether the store gets the briefing: the system result, unless the team overrode it."""
    if override == "incluida":
        return True
    if override == "excluida":
        return False
    return eligible
