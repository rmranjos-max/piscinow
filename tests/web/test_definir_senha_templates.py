import pytest

from piscinow.web.app import TEMPLATES


def _render(area, **context):
    template = TEMPLATES.env.get_template(f"{area}_definir_senha.html")
    return template.render(request=None, token="tok", invalid=False, error=None, **context)


@pytest.mark.parametrize("area", ["loja", "prestador", "comprador"])
def test_email_is_read_only_and_prefilled_when_recovering_an_active_account(area):
    html = _render(area, email="dono@example.com", email_locked=True)

    assert 'value="dono@example.com"' in html
    assert "readonly" in html


@pytest.mark.parametrize("area", ["loja", "prestador", "comprador"])
def test_email_is_editable_on_first_access(area):
    html = _render(area, email=None, email_locked=False)

    assert "readonly" not in html
    assert 'name="email"' in html
