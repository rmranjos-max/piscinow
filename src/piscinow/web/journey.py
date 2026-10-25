from decimal import Decimal

# The four fixed payment stages, in order. Labels are what the buyer reads.
STAGE_LABELS = {
    "terraplanagem": "Terraplanagem",
    "estrutura": "Estrutura",
    "revestimento": "Revestimento",
    "acabamento": "Acabamento",
}

_STAGE_STATE = {
    "sem": ("Sem itens neste cronograma", ""),
    "retido": ("Valor retido", "amber"),
    "parcial": ("Parcialmente liberado", "amber"),
    "liberado": ("Repasse liberado", "green"),
}


def comprador_journey(*, has_product: bool, confirmed: bool, payment_status: str | None, all_released: bool) -> dict:
    """Where the buyer is in the real flow, and the one thing to do next.

    Only states the system really has: no step is shown as done unless the data says so.
    """
    paid = payment_status == "pago"
    done = [has_product, confirmed, paid, paid and all_released]
    current = next((i for i, finished in enumerate(done) if not finished), None)
    steps = [
        {"label": label, "state": "done" if done[i] else ("current" if i == current else "")}
        for i, label in enumerate(
            ["Escolher produto e serviços", "Confirmar o projeto", "Cronograma e pagamento", "Repasse por fase"]
        )
    ]

    if not has_product:
        nxt = ("Escolha o seu produto", "Explore a vitrine e escolha a piscina ou o equipamento do projeto.",
               "/vitrine/produtos", "Explorar produtos")
    elif not confirmed:
        nxt = ("Revise e confirme o projeto", "Quando estiver tudo certo, confirme para a equipe montar o cronograma de pagamento.",
               "/comprador/projeto", "Revisar projeto")
    elif payment_status is None:
        nxt = ("Aguardando o cronograma", "A equipe Piscinow está montando o cronograma de pagamento por fase do seu projeto.",
               None, None)
    elif not paid:
        nxt = ("Pagamento pendente", "O cronograma está pronto. Confira as fases e os valores.",
               "/comprador/projeto/pagamento", "Ver pagamento")
    elif not all_released:
        nxt = ("Acompanhe os repasses", "O valor está retido e é repassado fase a fase pela equipe.",
               "/comprador/obra", "Acompanhar fases")
    else:
        nxt = ("Todos os repasses foram liberados", "As quatro fases do cronograma já tiveram o valor repassado.",
               "/comprador/obra", "Ver fases")
    title, text, href, cta = nxt
    return {"steps": steps, "next": {"title": title, "text": text, "href": href, "cta": cta}}


def stage_overview(rows) -> list[dict]:
    """rows: (stage, allocation status, amount, recipient name). One entry per fixed stage.

    A release is a payout, not a statement that the work is finished: the wording says so.
    """
    overview = []
    for key, label in STAGE_LABELS.items():
        items = [(status, amount, name) for stage, status, amount, name in rows if stage == key]
        if not items:
            state = "sem"
        elif all(status == "liberado" for status, _, _ in items):
            state = "liberado"
        elif any(status == "liberado" for status, _, _ in items):
            state = "parcial"
        else:
            state = "retido"
        state_label, tone = _STAGE_STATE[state]
        overview.append({
            "key": key,
            "label": label,
            "state": state,
            "state_label": state_label,
            "tone": tone,
            "lines": [{"name": name, "amount": amount, "released": status == "liberado"} for status, amount, name in items],
            "total": sum((amount for _, amount, _ in items), Decimal("0")),
        })
    return overview
