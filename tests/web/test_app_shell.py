from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from piscinow.web.app import create_app
from piscinow.web.navigation import AREAS

STATIC = Path(__file__).resolve().parents[2] / "src" / "piscinow" / "static"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    return TestClient(create_app())


@pytest.mark.parametrize("area_key", list(AREAS))
def test_the_shell_shows_the_menu_and_logout_of_each_area(client, area_key):
    area = AREAS[area_key]

    html = client.get(f"/_galeria/{area_key}").text

    assert 'lang="pt-BR"' in html
    assert f'action="{area.logout}"' in html
    for item in area.items:
        assert f'href="{item.href}"' in html


def test_the_shell_marks_the_current_page_with_aria_current(client):
    html = client.get("/_galeria/admin").text

    assert html.count('aria-current="page"') == 1


def test_the_shell_offers_a_skip_link_and_a_labelled_navigation(client):
    html = client.get("/_galeria").text

    assert 'class="skip-link" href="#conteudo"' in html
    assert 'id="conteudo"' in html
    assert 'aria-label="Menu principal"' in html


def test_the_shell_loads_only_its_own_stylesheet_and_no_third_party_fonts(client):
    html = client.get("/_galeria").text

    assert '/static/css/app-ui.css' in html
    assert "googleapis" not in html and "gstatic" not in html
    css = (STATIC / "css" / "app-ui.css").read_text(encoding="utf-8")
    assert "googleapis" not in css and "gstatic" not in css


def test_the_font_files_referenced_by_the_stylesheet_exist():
    import re

    css = (STATIC / "css" / "app-ui.css").read_text(encoding="utf-8")
    files = re.findall(r"url\(['\"]?(/static/fonts/[^'\")]+)", css)

    assert files, "no self-hosted font declared"
    for url in files:
        assert (STATIC / url.removeprefix("/static/")).is_file(), url


def test_the_shell_uses_no_inline_event_handlers_or_inline_styles(client):
    html = client.get("/_galeria").text

    assert "onclick=" not in html
    assert 'style="' not in html


def test_the_gallery_shows_every_shared_component(client):
    html = client.get("/_galeria").text

    for marker in ["data-component=\"badge\"", "data-component=\"stat\"", "data-component=\"notice\"",
                   "data-component=\"stepper\"", "data-component=\"timeline\"", "data-component=\"empty\""]:
        assert marker in html


MIGRATED = """admin_compradores admin_corrections admin_cronograma admin_lojas admin_pagamento_detalhe admin_pagamentos
admin_prestadores admin_queue comprador_pagamento comprador_projeto loja_produto_editar loja_produtos
prestador_servico_editar prestador_servicos""".split()


@pytest.mark.parametrize("name", MIGRATED)
def test_migrated_templates_use_the_shell_with_no_old_header_and_no_inline_style(name):
    from piscinow.web.app import TEMPLATES

    source = (STATIC.parent / "web" / "templates" / f"{name}.html").read_text(encoding="utf-8")

    assert 'extends "app_shell.html"' in source
    assert "{% block title %}" in source
    assert "admin-topbar" not in source and "admin-shell" not in source and 'class="wrap' not in source
    assert 'style="' not in source
    TEMPLATES.env.get_template(f"{name}.html")  # compiles


PAGES = {
    "admin_lojas": ("Lojas aprovadas", "/admin/lojas"),
    "admin_pagamentos": ("Projetos aguardando cronograma", "/admin/pagamentos"),
    "loja_produtos": ("Meus produtos", "/loja/produtos"),
    "comprador_pagamento": ("Pagamento do projeto", "/comprador/projeto"),
    "comprador_inicio": ("Olá, Marina.", "/comprador"),
    "comprador_obra": ("Acompanhar obra", "/comprador/obra"),
    "vitrine_produtos_comprador": ("Produtos", "/vitrine/produtos"),
}


@pytest.mark.parametrize("name", list(PAGES))
def test_the_gallery_renders_real_pages_with_example_data_inside_the_shell(client, name):
    heading, active_href = PAGES[name]

    response = client.get(f"/_galeria/pagina/{name}")

    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text
    assert f'href="{active_href}" aria-current="page"' in response.text


def test_the_gallery_page_route_is_404_for_unknown_pages_and_in_production(monkeypatch):
    monkeypatch.delenv("PISCINOW_ENVIRONMENT", raising=False)
    assert TestClient(create_app()).get("/_galeria/pagina/nao-existe").status_code == 404

    monkeypatch.setenv("PISCINOW_ENVIRONMENT", "production")
    monkeypatch.setenv("PISCINOW_SESSION_SECRET", "s" * 40)
    assert TestClient(create_app()).get("/_galeria/pagina/admin_lojas").status_code == 404


def test_the_brand_name_is_one_word_with_no_gap_between_its_parts(client):
    html = client.get("/_galeria").text

    assert '<span class="brand-text">pisci<span>now</span></span>' in html


def test_the_gallery_can_force_the_dark_or_light_theme_for_review(client):
    assert 'data-theme="dark"' in client.get("/_galeria?tema=escuro").text
    assert 'data-theme="light"' in client.get("/_galeria?tema=claro").text
    assert "data-theme" not in client.get("/_galeria").text


def test_the_vitrine_for_a_visitor_uses_the_public_layout_and_shows_no_price_or_buy_action(client):
    html = client.get("/_galeria/pagina/vitrine_produtos_visitante").text

    assert "<h1>Produtos</h1>" in html
    assert 'class="public-top"' in html and 'href="/comprador/login"' in html
    assert 'class="sidebar"' not in html
    assert "18.000,00" not in html and "18000" not in html
    assert "Pre&ccedil;o" not in html and "Escolher" not in html
    assert "Entrar para ver pre&ccedil;o e montar projeto" in html


def test_the_vitrine_for_a_comprador_shows_the_price_and_the_choose_action_inside_the_app(client):
    html = client.get("/_galeria/pagina/vitrine_produtos_comprador").text

    assert 'class="sidebar"' in html
    assert "R$ 18.000,00" in html and "Escolher" in html


def test_the_comprador_home_shows_the_real_next_step_and_the_project_summary(client):
    html = client.get("/_galeria/pagina/comprador_inicio").text

    assert "Acompanhe os repasses" in html
    assert "Piscina de fibra 7 x 3" in html
    assert "R$ 21.000,00" in html
    assert html.count('aria-current="step"') == 1


def test_the_stage_tracking_page_shows_the_four_stages_and_never_calls_a_payout_a_finished_work(client):
    html = client.get("/_galeria/pagina/comprador_obra").text

    for label in ["Terraplanagem", "Estrutura", "Revestimento", "Acabamento"]:
        assert label in html
    assert "Repasse liberado" in html and "Valor retido" in html
    assert "conclu" not in html.lower()
