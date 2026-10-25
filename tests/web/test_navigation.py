import pytest
from fastapi.testclient import TestClient

from piscinow.web.app import create_app
from piscinow.web.navigation import AREAS, area_for_path, nav_items_for


def _paths_with(app, method: str) -> set[str]:
    # app.routes returns included routers as blocks; the OpenAPI schema lists every path with its methods.
    return {path for path, methods in app.openapi()["paths"].items() if method in methods}


def test_each_area_is_resolved_from_the_route_prefix_not_from_the_session():
    assert area_for_path("/admin/fila").key == "admin"
    assert area_for_path("/loja/produtos/123/editar").key == "loja"
    assert area_for_path("/prestador/servicos").key == "prestador"
    assert area_for_path("/comprador/projeto/pagamento").key == "comprador"


def test_paths_outside_any_area_have_no_shell():
    assert area_for_path("/") is None
    assert area_for_path("/vitrine/produtos") is None
    assert area_for_path("/administrador") is None


def test_the_current_page_and_its_sub_pages_mark_one_item_as_active():
    items = nav_items_for(AREAS["comprador"], "/comprador/projeto/pagamento")

    active = [item for item in items if item["active"]]
    assert [item["label"] for item in active] == ["Meu projeto"]


def test_a_path_that_only_shares_a_prefix_does_not_activate_an_item():
    items = nav_items_for(AREAS["admin"], "/admin/lojas-extras")

    assert not any(item["active"] for item in items)


def test_every_menu_link_points_to_a_route_that_exists(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    get_paths = _paths_with(create_app(), "get")

    dead = [
        (area.key, item.href)
        for area in AREAS.values()
        for item in area.items
        if item.href not in get_paths
    ]

    assert dead == []


def test_every_area_has_a_logout_that_exists_as_a_post_route(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    post_paths = _paths_with(create_app(), "post")

    assert all(area.logout in post_paths for area in AREAS.values())


def test_the_component_gallery_exists_in_development_only(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    assert TestClient(create_app()).get("/_galeria").status_code == 200

    monkeypatch.setenv("PISCINOW_ENVIRONMENT", "production")
    monkeypatch.setenv("PISCINOW_SESSION_SECRET", "s" * 40)
    assert TestClient(create_app()).get("/_galeria").status_code == 404


def test_an_unknown_gallery_area_is_404(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)

    assert TestClient(create_app()).get("/_galeria/nao-existe").status_code == 404


def _active_labels(area_key: str, path: str) -> list[str]:
    return [item["label"] for item in nav_items_for(AREAS[area_key], path) if item["active"]]


def test_the_comprador_menu_follows_the_v3_order_and_starts_at_the_home_page():
    labels = [item.label for item in AREAS["comprador"].items]

    assert labels == ["Início", "Consultor", "Propostas", "Explorar produtos", "Explorar serviços", "Meu projeto", "Acompanhar obra"]
    assert AREAS["comprador"].home == "/comprador"


def test_the_home_item_is_active_only_on_the_home_page_itself():
    assert _active_labels("comprador", "/comprador") == ["Início"]
    assert _active_labels("comprador", "/comprador/obra") == ["Acompanhar obra"]
    assert _active_labels("comprador", "/comprador/projeto") == ["Meu projeto"]
    assert _active_labels("comprador", "/vitrine/produtos") == ["Explorar produtos"]
