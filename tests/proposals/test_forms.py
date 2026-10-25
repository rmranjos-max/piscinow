from datetime import date
from decimal import Decimal

from piscinow.proposals.forms import parse_proposal_form


def parse(**overrides):
    base = dict(
        item_desc=["Piscina", "Instalação", "", ""], item_amount=["18000,00", "3000", "", ""], scope="Escopo",
        lead_time_days="45", valid_until="2026-12-01", exclusions="",
    )
    return parse_proposal_form(**{**base, **overrides})


def test_filled_rows_become_items_and_blank_rows_are_ignored():
    values, errors = parse()

    assert errors == []
    assert values["items"] == [("Piscina", Decimal("18000.00")), ("Instalação", Decimal("3000"))]
    assert (values["lead_time_days"], values["valid_until"]) == (45, date(2026, 12, 1))


def test_a_description_without_an_amount_or_an_amount_without_a_description_is_an_error():
    assert parse(item_desc=["Piscina"], item_amount=[""])[1] == ["Informe um valor válido para o item 1 (ex.: 18000,00)."]
    assert parse(item_desc=[""], item_amount=["100"])[1] == ["O item 1 tem valor mas não tem descrição."]


def test_an_ambiguous_amount_is_not_guessed():
    assert parse(item_desc=["Piscina"], item_amount=["18.000,50"])[1]


def test_bad_days_and_dates_are_reported_together():
    values, errors = parse(lead_time_days="abc", valid_until="amanhã")

    assert values is None
    assert len(errors) == 2


def test_mismatched_list_lengths_do_not_crash():
    values, errors = parse(item_desc=["Piscina", "Extra"], item_amount=["100"])

    assert values is None and len(errors) == 1
