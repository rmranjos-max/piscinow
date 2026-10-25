import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from piscinow.web.journey import comprador_journey, stage_overview
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
    "comprador_pagamento": ("comprador_pagamento.html", "comprador", "/comprador/projeto"),
    "comprador_inicio": ("comprador_inicio.html", "comprador", "/comprador"),
    "comprador_obra": ("comprador_obra.html", "comprador", "/comprador/obra"),
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
        }
    if name == "comprador_obra":
        rows = [
            ("estrutura", "liberado", Decimal("18000.00"), "Studio Fibra Sul"),
            ("acabamento", "retido", Decimal("3000.00"), "Instalações Sul"),
        ]
        return {"payment": NS(total_amount=Decimal("21000.00"), status=NS(value="pago")), "stages": stage_overview(rows)}
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
