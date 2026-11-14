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
    assert values["items"] == [("Piscina", Decimal("18000.00"), None), ("Instalação", Decimal("3000"), None)]
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


def test_an_item_can_point_to_a_catalog_product_and_leave_description_and_amount_to_it():
    values, errors = parse(item_desc=["", "Instalação"], item_amount=["", "3000"], item_product=["abc-123", ""])

    assert errors == []
    assert values["items"] == [("", None, "abc-123"), ("Instalação", Decimal("3000"), None)]


def test_a_typed_amount_wins_over_the_catalog_price_but_must_still_be_valid():
    assert parse(item_desc=[""], item_amount=["17500,00"], item_product=["abc"])[0]["items"] == [("", Decimal("17500.00"), "abc")]
    assert parse(item_desc=[""], item_amount=["17.500,00"], item_product=["abc"])[1]


def test_a_row_with_nothing_but_an_empty_product_choice_is_ignored():
    values, errors = parse(item_desc=["Piscina", ""], item_amount=["100", ""], item_product=["", ""])

    assert errors == [] and len(values["items"]) == 1
