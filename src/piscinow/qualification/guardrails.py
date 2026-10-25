import re
import unicodedata

SAFE_FALLBACK = (
    "Vou confirmar essa informação com a nossa equipe e já te retorno. "
    "Enquanto isso, posso seguir com algumas perguntas sobre o seu projeto?"
)

# The fixed budget-range labels the agent may offer as suggestions (they are not product prices).
_RANGE_NUMBERS = {30, 50}

_MONEY_WITH_SYMBOL = re.compile(r"r\$\s*(\d[\d.,]*)")
_MONEY_WITH_WORD = re.compile(r"(\d[\d.,]*)\s*(?:mil\b|reais\b|k\b)")
_ANY_NUMBER = re.compile(r"\d[\d.,]*")

_RULES = {
    "promessa": re.compile(
        r"\bgaranto\b|\bgarantimos\b|\bgarantia de\b|\bprometo\b|\bprometemos\b"
        r"|prazo de entrega de \d+|\bfica pronta em \d+|\bentrego em \d+"
    ),
    "preco_futuro": re.compile(r"\bprecos? (vao|vai|tende|tendem|devem|deve)\s+(a )?(subir|aumentar|mudar|dobrar)"),
    "afirma_ser_humano": re.compile(
        r"\bsou (uma |um )?(pessoa|humano|humana|atendente humano|gente de verdade)\b"
        r"|\bnao sou (um |uma )?(robo|bot|ia|inteligencia artificial|assistente virtual|maquina)\b"
    ),
    "disponibilidade": re.compile(
        r"\bem estoque\b|\bpronta entrega\b|\bdisponibilidade (garantida|imediata)\b|\bdisponivel imediatamente\b"
    ),
}


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _to_int(token: str) -> int | None:
    token = token.rstrip(".,")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", token):
        return int(re.sub(r"[.,]", "", token))
    digits = re.split(r"[.,]", token)[0]
    return int(digits) if digits else None


def _numbers_in(text: str) -> set[int]:
    return {n for n in (_to_int(t) for t in _ANY_NUMBER.findall(text)) if n is not None}


def check_reply(reply: str, user_texts: list[str]) -> list[str]:
    """Reasons to reject an agent reply. Empty list means it may be sent."""
    folded = _fold(reply)
    violations = []

    allowed = _RANGE_NUMBERS | _numbers_in(_fold(" ".join(user_texts)))
    mentioned = {
        _to_int(m) for pattern in (_MONEY_WITH_SYMBOL, _MONEY_WITH_WORD) for m in pattern.findall(folded)
    }
    if any(n is not None and n not in allowed for n in mentioned):
        violations.append("valor_nao_informado")

    for name, pattern in _RULES.items():
        if pattern.search(folded):
            violations.append(name)
    return violations
