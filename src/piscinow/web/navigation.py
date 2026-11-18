from dataclasses import dataclass


@dataclass(frozen=True)
class NavItem:
    label: str
    href: str
    icon: str
    exact: bool = False


@dataclass(frozen=True)
class Area:
    key: str
    label: str
    prefix: str
    home: str
    logout: str
    items: tuple[NavItem, ...]


# Only routes that exist. A test fails if a menu link points nowhere.
AREAS: dict[str, Area] = {
    "admin": Area(
        key="admin",
        label="Administração",
        prefix="/admin",
        home="/admin/fila",
        logout="/admin/logout",
        items=(
            NavItem("Visão geral", "/admin", "home", exact=True),
            NavItem("Fila de admissão", "/admin/fila", "inbox"),
            NavItem("Oportunidades", "/admin/oportunidades", "target"),
            NavItem("Lojas", "/admin/lojas", "store"),
            NavItem("Prestadores", "/admin/prestadores", "wrench"),
            NavItem("Compradores", "/admin/compradores", "users"),
            NavItem("Pagamentos", "/admin/pagamentos", "wallet"),
            NavItem("Ensinar o concierge", "/admin/correcoes", "book"),
            NavItem("Governança", "/admin/governanca", "shield"),
        ),
    ),
    "loja": Area(
        key="loja",
        label="Loja parceira",
        prefix="/loja",
        home="/loja/produtos",
        logout="/loja/logout",
        items=(
            NavItem("Oportunidades", "/loja/oportunidades", "target"),
            NavItem("Meus produtos", "/loja/produtos", "box"),
        ),
    ),
    "prestador": Area(
        key="prestador",
        label="Instalador",
        prefix="/prestador",
        home="/prestador/servicos",
        logout="/prestador/logout",
        items=(
            NavItem("Instalações", "/prestador/instalacoes", "flag"),
            NavItem("Meus serviços", "/prestador/servicos", "wrench"),
        ),
    ),
    "comprador": Area(
        key="comprador",
        label="Comprador",
        prefix="/comprador",
        home="/comprador",
        logout="/comprador/logout",
        items=(
            NavItem("Início", "/comprador", "home", exact=True),
            NavItem("Consultor", "/comprador/consultor", "chat"),
            NavItem("Propostas", "/comprador/propostas", "doc"),
            NavItem("Meu projeto", "/comprador/projeto", "folder"),
            NavItem("Explorar piscinas", "/vitrine/produtos", "compass"),
        ),
    ),
}


def area_for_path(path: str) -> Area | None:
    # The area comes from the URL, never from the session: one browser can hold
    # sessions of several profiles at the same time.
    for area in AREAS.values():
        if path == area.prefix or path.startswith(area.prefix + "/"):
            return area
    return None


def _is_active(item: NavItem, path: str) -> bool:
    if item.exact:
        return path.rstrip("/") == item.href
    return path == item.href or path.startswith(item.href + "/")


def nav_items_for(area: Area, path: str) -> list[dict]:
    return [
        {"label": item.label, "href": item.href, "icon": item.icon, "active": _is_active(item, path)}
        for item in area.items
    ]


# Short confirmations after an action, chosen by code so a link can never inject text.
FLASH = {
    "salvo": "Alterações salvas.",
    "enviada": "Enviada.",
    "mensagem": "Mensagem enviada.",
    "revisao": "Pedido de revisão enviado. A loja foi avisada.",
    "recusada": "Proposta recusada. A loja viu o motivo.",
    "aceita": "Proposta aceita.",
    "resposta": "Resposta registrada.",
    "proposta": "Proposta enviada ao comprador.",
    "cronograma": "Cronograma salvo.",
    "viabilidade": "Viabilidade salva.",
    "atribuido": "Instalador atribuído.",
    "matching": "Matching executado.",
    "encaminhada": "Briefing encaminhado às lojas.",
    "revisada": "Revisão registrada.",
    "perdida": "Oportunidade marcada como perdida.",
}


def shell_context(request) -> dict:
    forced = request.scope.get("shell_area")
    area = AREAS.get(forced) if forced else area_for_path(request.url.path)
    if area is None:
        return {}
    # The component gallery pins a path so a menu item shows as active.
    path = request.scope.get("shell_path", request.url.path)
    return {
        "flash": FLASH.get(request.query_params.get("ok", "")),
        "shell": {
            "label": area.label,
            "home": area.home,
            "logout": area.logout,
            "items": nav_items_for(area, path),
        }
    }
