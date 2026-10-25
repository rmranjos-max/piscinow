import pytest

from piscinow.qualification.fields import FIELDS, REQUIRED, label_for, normalize_field


def test_the_minimum_to_open_an_opportunity_is_location_type_and_deadline():
    assert REQUIRED == ("localizacao", "tipo_piscina", "prazo")


@pytest.mark.parametrize(
    "key, raw, expected",
    [
        ("tipo_piscina", "fibra", "fibra"),
        ("tipo_piscina", "  Fibra ", "fibra"),
        ("tipo_piscina", "Ainda não sei", "ainda_nao_sei"),
        ("prazo", "Até 90 dias", "ate_90_dias"),
        ("prazo", "ate_6_meses", "ate_6_meses"),
        ("orcamento", "R$ 30 a 50 mil", "30_a_50_mil"),
        ("terreno", "Plano, acesso livre", "plano_acesso_livre"),
    ],
)
def test_choice_fields_accept_the_stored_value_or_its_label_ignoring_case_and_accents(key, raw, expected):
    assert normalize_field(key, raw) == expected


@pytest.mark.parametrize("key, raw", [("tipo_piscina", "titânio"), ("prazo", "ontem"), ("orcamento", "um milhão")])
def test_choice_fields_reject_anything_outside_the_catalog(key, raw):
    assert normalize_field(key, raw) is None


def test_free_text_fields_are_trimmed_and_whitespace_is_collapsed():
    assert normalize_field("localizacao", "  Valinhos \n  SP ") == "Valinhos SP"


def test_free_text_fields_are_truncated_to_their_limit():
    long_text = "x" * 500

    assert len(normalize_field("localizacao", long_text)) == FIELDS["localizacao"].max_length


@pytest.mark.parametrize("raw", ["", "   ", None, "não sei", "N/A", "-"])
def test_empty_or_meaningless_free_text_is_rejected(raw):
    assert normalize_field("localizacao", raw) is None


def test_values_that_are_not_text_are_rejected_instead_of_crashing():
    assert normalize_field("localizacao", {"cidade": "Valinhos"}) is None
    assert normalize_field("localizacao", ["Valinhos"]) is None


def test_unknown_fields_are_rejected():
    assert normalize_field("cpf", "123") is None


def test_labels_are_human_readable():
    assert label_for("tipo_piscina", "ainda_nao_sei") == "Ainda não sei"
    assert label_for("prazo", "ate_90_dias") == "Até 90 dias"
    assert label_for("localizacao", "Valinhos") == "Valinhos"
