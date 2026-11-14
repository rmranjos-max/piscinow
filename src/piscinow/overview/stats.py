from datetime import datetime, timedelta

# Pipeline order of the deal states, with what the team reads.
PIPELINE = (
    ("qualified", "Qualificada"),
    ("matched", "Lojas indicadas"),
    ("partner_review", "Em análise pela loja"),
    ("proposal_sent", "Proposta enviada"),
    ("negotiating", "Em negociação"),
    ("accepted", "Aceita"),
    ("lost", "Perdida"),
    ("cancelled", "Cancelada"),
)


def funnel(counts: dict[str, int]) -> list[dict]:
    """Every pipeline state in order, with its count and its share of the largest state."""
    biggest = max((counts.get(key, 0) for key, _ in PIPELINE), default=0)
    return [
        {
            "key": key, "label": label, "count": counts.get(key, 0),
            "share": round(counts.get(key, 0) * 100 / biggest) if biggest else 0,
        }
        for key, label in PIPELINE
    ]


def loss_reasons(reasons, limit: int = 5) -> list[tuple[str, int]]:
    """The most frequent loss reasons, grouped ignoring case and extra spaces."""
    groups: dict[str, list] = {}
    for raw in reasons:
        text = " ".join((raw or "").split())
        if not text:
            continue
        entry = groups.setdefault(text.lower(), [text, 0])
        entry[1] += 1
    ranked = sorted(groups.values(), key=lambda entry: -entry[1])
    return [(text, count) for text, count in ranked[:limit]]


def average_duration(pairs: list[tuple[datetime, datetime]]) -> timedelta | None:
    deltas = [end - start for start, end in pairs if end >= start]
    return sum(deltas, timedelta()) / len(deltas) if deltas else None


def format_duration(delta: timedelta | None) -> str:
    if delta is None:
        return "—"
    minutes = int(delta.total_seconds() // 60)
    days, rest = divmod(minutes, 24 * 60)
    hours = rest // 60
    if days:
        unit = "dia" if days == 1 else "dias"
        return f"{days} {unit} e {hours} h" if hours else f"{days} {unit}"
    if hours:
        return f"{hours} h"
    return f"{minutes} min"
