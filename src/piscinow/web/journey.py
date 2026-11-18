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


JOURNEY_STEPS = ("Briefing", "Propostas", "Aceite", "Pagamento por fases", "Obra")
_BEFORE_ACCEPTANCE = ("qualified", "matched", "partner_review", "proposal_sent", "negotiating")


def _next(title: str, text: str, href: str | None = None, cta: str | None = None) -> dict:
    return {"title": title, "text": text, "href": href, "cta": cta}


def buyer_journey(
    *, briefing: str, deal_status: str | None, open_proposals: int, payment_status: str | None,
    all_released: bool, project_linked: bool,
) -> dict:
    """The single buyer journey: Briefing, Propostas, Aceite, Pagamento por fases, Obra.

    briefing is "none", "in_progress", "declined" or "done". Only what the data says is shown as
    done; `project_linked` covers both a project from an accepted proposal and an old-path project
    that already has a payment.
    """
    accepted = deal_status == "accepted" or project_linked
    paid = payment_status == "pago"
    done = [
        briefing == "done" or accepted or deal_status is not None,
        accepted, accepted, paid, paid and all_released,
    ]
    current = next((i for i, finished in enumerate(done) if not finished), None)
    steps = [
        {"label": label, "state": "done" if done[i] else ("current" if i == current else "")}
        for i, label in enumerate(JOURNEY_STEPS)
    ]

    consultor = "/comprador/consultor"
    if accepted:
        if payment_status is None:
            nxt = _next("A equipe está preparando o pagamento", "A proposta foi aceita. A equipe monta o pagamento por fases a partir dela e avisa por aqui.")
        elif not paid:
            nxt = _next("Pagamento pendente", "O pagamento por fases está pronto. Confira as fases e os valores.", "/comprador/projeto/pagamento", "Ver pagamento")
        elif not all_released:
            nxt = _next("Acompanhe a obra", "O valor fica retido e é repassado fase a fase pela equipe.", "/comprador/obra", "Acompanhar a obra")
        else:
            nxt = _next("Todos os repasses foram liberados", "As fases do pagamento já tiveram o valor repassado.", "/comprador/obra", "Ver a obra")
    elif deal_status in ("lost", "cancelled"):
        nxt = _next("Quer retomar o projeto?", "Esta oportunidade foi encerrada. Converse com a assistente para recomeçar quando quiser.", consultor, "Conversar com a assistente")
    elif deal_status in ("qualified", "matched"):
        nxt = _next("A equipe está escolhendo as lojas", "Seu briefing foi autorizado. A equipe indica lojas compatíveis e elas vão analisar o seu projeto.")
    elif deal_status in _BEFORE_ACCEPTANCE:
        if open_proposals:
            title = "Compare a proposta que chegou" if open_proposals == 1 else f"Compare as {open_proposals} propostas que chegaram"
            nxt = _next(title, "Você pode conversar com a loja, pedir ajustes e aceitar quando estiver seguro.", "/comprador/propostas", "Ver as propostas")
        else:
            nxt = _next("As lojas estão analisando", "As lojas indicadas estão analisando o seu projeto. As propostas aparecem aqui.", "/comprador/propostas", "Abrir propostas")
    elif briefing == "declined":
        nxt = _next("Seu briefing está pronto", "Quando quiser, autorize o compartilhamento, sem nome e sem contato, com lojas compatíveis.", consultor, "Revisar e autorizar")
    elif briefing == "in_progress":
        nxt = _next("Termine o seu briefing", "Faltam poucas informações para as lojas poderem propor.", consultor, "Continuar a conversa")
    else:
        nxt = _next("Conte o que você imagina", "A nossa assistente faz algumas perguntas e monta o briefing que as lojas recebem.", consultor, "Conversar com a assistente")
    return {"steps": steps, "next": nxt}


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


def consultor_card(*, started: bool, missing: list[str], consent: str, deal_code: str | None) -> dict:
    """The home-page card about the briefing and the opportunity. Says only what the data says."""
    href = "/comprador/consultor"
    if not started:
        return {"badge": "Não iniciado", "tone": "", "title": "Conte o que você imagina",
                "text": "Converse com a nossa assistente. Em poucos minutos ela monta o briefing que as lojas do Clube recebem.",
                "href": href, "cta": "Conversar com a assistente"}
    if consent == "concedido":
        text = (f"A oportunidade {deal_code} está com a nossa equipe, que avisa as lojas compatíveis."
                if deal_code else "Você autorizou o compartilhamento e a nossa equipe está acompanhando.")
        return {"badge": "Em acompanhamento", "tone": "green", "title": "Seu briefing foi compartilhado",
                "text": text, "href": href, "cta": "Ver o briefing"}
    if missing:
        return {"badge": "Em construção", "tone": "amber", "title": "Seu briefing está em andamento",
                "text": "Ainda falta: " + ", ".join(missing) + ".", "href": href, "cta": "Continuar a conversa"}
    return {"badge": "Falta a sua decisão", "tone": "amber", "title": "Seu briefing está pronto",
            "text": "Falta só você decidir se autoriza compartilhar o briefing, sem nome e sem contato, com lojas compatíveis.",
            "href": href, "cta": "Revisar e autorizar"}


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
