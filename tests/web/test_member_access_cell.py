import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from piscinow.web.app import TEMPLATES


def _render(**member_fields):
    fields = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "password_hash": None,
        "set_password_token": None,
        "set_password_token_expires_at": None,
        **member_fields,
    }
    member = SimpleNamespace(**fields)
    template = TEMPLATES.env.get_template("_member_access_cell.html")
    return template.render(member=member, base_url="https://clube.example", area="loja")


def test_active_member_without_pending_link_offers_to_generate_a_new_password_link():
    html = _render(password_hash="hash")

    assert "Ativo" in html
    assert "Gerar link de nova senha" in html
    assert "/admin/membros/11111111-1111-1111-1111-111111111111/novo-link-senha" in html
    assert "definir-senha" not in html


def test_active_member_with_a_pending_reset_shows_the_link_and_its_expiry():
    html = _render(
        password_hash="hash",
        set_password_token="tok123",
        set_password_token_expires_at=datetime(2026, 10, 26, 14, 3, tzinfo=timezone.utc),
    )

    assert "https://clube.example/loja/definir-senha/tok123" in html
    assert "redefini" in html
    assert "26/10 14:03" in html


def test_member_waiting_for_first_access_shows_the_link():
    html = _render(
        set_password_token="tok456",
        set_password_token_expires_at=datetime(2026, 11, 1, 9, 0, tzinfo=timezone.utc),
    )

    assert "Aguardando defini" in html
    assert "https://clube.example/loja/definir-senha/tok456" in html
    assert "Gerar novo link de acesso" in html


def test_member_with_no_access_yet_can_get_a_link_generated():
    html = _render()

    assert "Sem acesso gerado" in html
    assert "Gerar novo link de acesso" in html
