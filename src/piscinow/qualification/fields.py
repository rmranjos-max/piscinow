import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class FieldDef:
    key: str
    label: str
    required: bool
    choices: dict[str, str] | None = None  # stored value -> label shown to people
    max_length: int = 100


# Order here is the order of the briefing.
FIELDS: dict[str, FieldDef] = {
    "localizacao": FieldDef("localizacao", "Localização", True, max_length=100),
    "tipo_piscina": FieldDef(
        "tipo_piscina", "Tipo de piscina", True,
        {"fibra": "Fibra", "vinil": "Vinil", "alvenaria": "Alvenaria", "ainda_nao_sei": "Ainda não sei"},
    ),
    "dimensoes": FieldDef("dimensoes", "Dimensões", False, max_length=60),
    "prazo": FieldDef(
        "prazo", "Prazo desejado", True,
        {"ate_90_dias": "Até 90 dias", "ate_6_meses": "Até 6 meses",
         "mais_de_6_meses": "Mais de 6 meses", "sem_prazo": "Sem prazo definido"},
    ),
    "orcamento": FieldDef(
        "orcamento", "Orçamento", False,
        {"ate_30_mil": "Até R$ 30 mil", "30_a_50_mil": "R$ 30 a 50 mil",
         "acima_de_50_mil": "Acima de R$ 50 mil", "nao_informado": "Não informado"},
    ),
    "terreno": FieldDef(
        "terreno", "Terreno", False,
        {"plano_acesso_livre": "Plano, acesso livre", "inclinado": "Inclinado",
         "precisa_avaliacao": "Precisa de avaliação"},
    ),
    "finalidade": FieldDef("finalidade", "Finalidade", False, max_length=100),
}

REQUIRED = tuple(key for key, field in FIELDS.items() if field.required)

_MEANINGLESS = {"nao sei", "n/a", "na", "nada", "nenhum", "-", "--", "?"}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", " ", stripped.lower()).strip()


def normalize_field(key: str, raw) -> str | None:
    """Validated value for a field, or None. The model's output never reaches the database without this."""
    field = FIELDS.get(key)
    if field is None or not isinstance(raw, str):
        return None
    text = re.sub(r"\s+", " ", raw).strip()
    if not text:
        return None
    if field.choices is not None:
        wanted = _fold(text)
        for value, label in field.choices.items():
            if wanted in (_fold(value), _fold(label)):
                return value
        return None
    if _fold(text) in _MEANINGLESS or not re.search(r"\w", text):
        return None
    return text[: field.max_length].rstrip()


def label_for(key: str, value: str) -> str:
    field = FIELDS.get(key)
    if field is not None and field.choices is not None:
        return field.choices.get(value, value)
    return value
