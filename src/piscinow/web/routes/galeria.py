import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from piscinow.qualification.service import known_fields
from piscinow.web.journey import comprador_journey, consultor_card, stage_overview
from piscinow.web.navigation import AREAS

# Registered only in development (see create_app). Lists every shared component and every
# area's menu with example data, so the interface can be reviewed without a database.
router = APIRouter()


@router.get("/_galeria", response_class=HTMLResponse)
@router.get("/_galeria/{area}", response_class=HTMLResponse)
async def galeria(request: Request, area: str = "admin"):
    if area not in AREAS:
        raise HTTPException(status_code=404)
    request.scope["shell_area"] = area
    request.scope["shell_path"] = AREAS[area].items[0].href
    return request.app.state.templates.TemplateResponse(
        request, "galeria.html", {"area_key": area, "areas": AREAS, "pages": list(PAGES), "theme": _theme(request)}
    )


def _theme(request: Request) -> str | None:
    # ?tema=escuro|claro forces a theme so both can be reviewed regardless of the OS setting.
    return {"escuro": "dark", "claro": "light"}.get(request.query_params.get("tema", ""))


# Real templates rendered with example objects: name -> (template, area, menu path shown as active).
# An area of None renders the public layout (visitor), with no menu.
PAGES = {
    "admin_lojas": ("admin_lojas.html", "admin", "/admin/lojas"),
    "admin_pagamentos": ("admin_pagamentos.html", "admin", "/admin/pagamentos"),
    "loja_produtos": ("loja_produtos.html", "loja", "/loja/produtos"),
    "admin_oportunidades": ("admin_oportunidades.html", "admin", "/admin/oportunidades"),
    "admin_oportunidade_detalhe": ("admin_oportunidade_detalhe.html", "admin", "/admin/oportunidades"),
    "comprador_pagamento": ("comprador_pagamento.html", "comprador", "/comprador/projeto"),
    "comprador_inicio": ("comprador_inicio.html", "comprador", "/comprador"),
    "comprador_obra": ("comprador_obra.html", "comprador", "/comprador/obra"),
    "comprador_consultor": ("comprador_consultor.html", "comprador", "/comprador/consultor"),
    "comprador_consultor_completo": ("comprador_consultor.html", "comprador", "/comprador/consultor"),
    "vitrine_produtos_comprador": ("vitrine_produtos.html", "comprador", "/vitrine/produtos"),
    "vitrine_produtos_visitante": ("vitrine_produtos.html", None, "/vitrine/produtos"),
}


def _example_context(name: str) -> dict:
    now = datetime.now(timezone.utc)
    uid = lambda n: uuid.UUID(int=n)  # noqa: E731
    if name == "admin_lojas":
        return {
            "base_url": "https://clube.exemplo.com.br",
            "members": [
                NS(id=uid(11), name="Studio Fibra Sul", email="contato@studiofibra.exemplo", password_hash="h",
                   set_password_token=None, set_password_token_expires_at=None),
                NS(id=uid(12), name="Piscinas Campinas", email="vendas@piscinascampinas.exemplo", password_hash="h",
                   set_password_token="token-de-exemplo-redefinicao", set_password_token_expires_at=now + timedelta(hours=23)),
                NS(id=uid(13), name="Vinil & Cia", email=None, password_hash=None,
                   set_password_token="token-de-exemplo-primeiro-acesso", set_password_token_expires_at=now + timedelta(days=6)),
            ],
        }
    if name == "admin_pagamentos":
        paid = NS(value="pago")
        pending = NS(value="pendente")
        return {
            "items": [{"comprador": NS(name="Marina Duarte"), "product": NS(name="Piscina de fibra 7 x 3"), "project": NS(id=uid(21))}],
            "payments": [
                {"comprador": NS(name="Carlos Souza"), "payment": NS(id=uid(31), total_amount=Decimal("21000.00"), status=paid)},
                {"comprador": NS(name="Ana Lima"), "payment": NS(id=uid(32), total_amount=Decimal("18500.50"), status=pending)},
            ],
        }
    if name == "loja_produtos":
        return {
            "error": None, "note": None, "prefill": {},
            "products": [
                NS(id=uid(41), name="Piscina de fibra 7 x 3", category="fibra", price=Decimal("18000.00"), active=True),
                NS(id=uid(42), name="Kit de filtragem", category="filtragem", price=Decimal("3500.00"), active=True),
                NS(id=uid(43), name="Capa térmica", category="acessórios", price=Decimal("900.00"), active=False),
            ],
        }
    if name == "comprador_pagamento":
        stage = lambda value: NS(value=value)  # noqa: E731
        return {
            "error": None,
            "payment": NS(total_amount=Decimal("21000.00"), status=NS(value="pendente")),
            "allocations": [
                (NS(stage=stage("estrutura"), amount=Decimal("18000.00")), NS(name="Studio Fibra Sul")),
                (NS(stage=stage("acabamento"), amount=Decimal("3000.00")), NS(name="Instalações Sul")),
            ],
        }
    if name == "comprador_inicio":
        return {
            "first_name": "Marina", "project": NS(status=NS(value="confirmado")),
            "product": NS(name="Piscina de fibra 7 x 3", category="fibra"),
            "services": [NS(), NS()],
            "payment": NS(total_amount=Decimal("21000.00"), status=NS(value="pago")),
            "journey": comprador_journey(has_product=True, confirmed=True, payment_status="pago", all_released=False),
            "consultor": consultor_card(started=True, missing=[], consent="concedido", deal_code="OP-0007"),
        }
    if name == "comprador_obra":
        rows = [
            ("estrutura", "liberado", Decimal("18000.00"), "Studio Fibra Sul"),
            ("acabamento", "retido", Decimal("3000.00"), "Instalações Sul"),
        ]
        return {"payment": NS(total_amount=Decimal("21000.00"), status=NS(value="pago")), "stages": stage_overview(rows)}
    if name == "admin_oportunidades":
        filters = {"ativas": "Ativas", "todas": "Todas", "qualified": "Qualificada", "lost": "Perdida"}
        row = lambda n, buyer, summary, status, tone="", attention=False: {  # noqa: E731
            "deal": NS(code=f"OP-{n:04d}", created_at=now - timedelta(days=n)),
            "buyer": NS(name=buyer), "qualification": NS(id=uid(60 + n), attention_at=now if attention else None),
            "status": status, "tone": tone, "summary": summary,
        }
        return {
            "filters": filters, "estado": "ativas",
            "rows": [
                row(7, "Marina Duarte", "Fibra · Valinhos · Até 90 dias", "Qualificada", attention=True),
                row(6, "Carlos Souza", "Alvenaria · Campinas · Até 6 meses", "Em análise pela loja"),
                row(4, "Ana Lima", "Vinil · Vinhedo · Sem prazo definido", "Proposta enviada"),
            ],
            "waiting": [
                {"buyer": NS(name="Paulo Ribeiro"), "summary": "Fibra",
                 "qualification": NS(id=uid(90), attention_note="Sem resposta após 3 perguntas: Localização")},
            ],
        }
    if name == "admin_oportunidade_detalhe":
        field = lambda key, value, source="cliente": NS(  # noqa: E731
            key=key, value=value, source=NS(value=source), verification=NS(value="declarado")
        )
        qualification = NS(
            id=uid(67), attention_at=now, attention_note="Dúvida do comprador: quer saber o prazo de entrega de fibra",
            consent=NS(value="concedido"),
            fields=[field("localizacao", "Valinhos"), field("tipo_piscina", "fibra"), field("prazo", "ate_90_dias"),
                    field("dimensoes", "7 x 3 m", "admin")],
        )
        return {
            "qualification": qualification,
            "buyer": NS(name="Marina Duarte", email="marina@exemplo.com.br", phone="(19) 99999-0000", region="Campinas"),
            "deal": NS(code="OP-0007", lost_reason=None), "deal_status": "Qualificada", "closed": False,
            "briefing": known_fields(qualification),
            "events": [{"title": "Oportunidade criada", "detail": f"{now:%d/%m/%Y %H:%M} · sistema"}],
            "transcript": [
                {"from_agent": True, "text": "Oi, Marina! Eu sou a assistente virtual da Piscinow. Em que cidade fica o terreno?"},
                {"from_agent": False, "text": "Valinhos. Fibra, uns 7 por 3."},
            ],
            "field_keys": {"localizacao": "Localização", "prazo": "Prazo desejado"},
            "error": None,
        }
    if name in ("comprador_consultor", "comprador_consultor_completo"):
        complete = name.endswith("completo")
        field = lambda key, value, source="cliente", verification="declarado": NS(  # noqa: E731
            key=key, value=value, source=NS(value=source), verification=NS(value=verification)
        )
        fields = [field("localizacao", "Valinhos"), field("tipo_piscina", "fibra")]
        messages = [
            {"from_agent": True, "text": "Oi, Marina! Eu sou a assistente virtual da Piscinow. Em que cidade fica o terreno?"},
            {"from_agent": False, "text": "Valinhos. Estou pensando numa piscina de fibra."},
            {"from_agent": True, "text": "Ótima escolha! Fibra costuma ter uma instalação rápida. Para quando você imagina a obra?"},
        ]
        if complete:
            fields += [field("prazo", "ate_6_meses"), field("dimensoes", "7 x 3 m"), field("orcamento", "30_a_50_mil")]
            messages += [
                {"from_agent": False, "text": "Queria começar em uns 4 meses. Uns 7 por 3 metros, e posso investir de 30 a 50 mil."},
                {"from_agent": True, "text": "Perfeito, já tenho o essencial. Posso compartilhar o seu briefing, sem nome e sem contato, com lojas compatíveis?"},
            ]
        return {
            "messages": messages,
            "briefing": known_fields(NS(fields=fields)),
            "missing": [] if complete else ["Prazo desejado"],
            "consent": "nao_respondido",
            "attention": False,
            "unavailable": False,
        }
    if name in ("vitrine_produtos_comprador", "vitrine_produtos_visitante"):
        logged = name.endswith("comprador")
        return {
            "items": [
                {"product": NS(id=uid(51), name="Piscina de fibra 7 x 3", category="fibra", price=Decimal("18000.00")),
                 "loja": NS(name="Studio Fibra Sul", region="Valinhos")},
                {"product": NS(id=uid(52), name="Kit de filtragem", category="filtragem", price=Decimal("3500.00")),
                 "loja": NS(name="Piscinas Campinas", region="Campinas")},
            ],
            "kind": "", "category": "", "regiao": "",
            "comprador": NS(name="Marina Duarte") if logged else None,
            "layout": "app_shell.html" if logged else "public_shell.html",
        }
    raise KeyError(name)


@router.get("/_galeria/pagina/{name}", response_class=HTMLResponse)
async def pagina(request: Request, name: str):
    if name not in PAGES:
        raise HTTPException(status_code=404)
    template, area, active_path = PAGES[name]
    if area:
        request.scope["shell_area"] = area
        request.scope["shell_path"] = active_path
    context = {**_example_context(name), "theme": _theme(request)}
    return request.app.state.templates.TemplateResponse(request, template, context)
