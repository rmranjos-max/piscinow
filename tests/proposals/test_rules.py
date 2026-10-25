from datetime import date, timedelta
from decimal import Decimal

import pytest

from piscinow.proposals.rules import (
    FEASIBILITY_ITEMS,
    acceptance_blocker,
    caveats,
    is_expired,
    parse_amount,
    total_of,
    validate_feasibility,
    validate_proposal,
)

TODAY = date(2026, 10, 25)


@pytest.mark.parametrize("raw,expected", [
    ("18000", Decimal("18000")), ("18000,50", Decimal("18000.50")), ("18000.5", Decimal("18000.5")),
    (" 99,90 ", Decimal("99.90")), ("99999999.99", Decimal("99999999.99")),
])
def test_valid_amounts_are_parsed_as_decimal(raw, expected):
    assert parse_amount(raw) == expected
    assert isinstance(parse_amount(raw), Decimal)


@pytest.mark.parametrize("raw", [
    "", "  ", "abc", "0", "-5", "18.000,50", "18.000", "1,234", "10.123", "100000000", "NaN", "Infinity", None, "1e3",
])
def test_ambiguous_or_invalid_amounts_are_rejected_instead_of_guessed(raw):
    assert parse_amount(raw) is None


def test_the_total_is_the_exact_decimal_sum_of_the_items():
    assert total_of([Decimal("0.10"), Decimal("0.20"), Decimal("18000.00")]) == Decimal("18000.30")
    assert total_of([]) == Decimal("0")


def _valid(**overrides):
    base = dict(
        items=[("Piscina de fibra 7x3", Decimal("18000.00")), ("Instalação", Decimal("3000.00"))],
        scope="Fornecimento e instalação completa.", lead_time_days=45, valid_until=TODAY + timedelta(days=15), today=TODAY,
    )
    return validate_proposal(**{**base, **overrides})


def test_a_complete_proposal_has_no_errors():
    assert _valid() == []


def test_a_proposal_needs_at_least_one_item():
    assert _valid(items=[]) == ["Inclua ao menos um item na proposta."]


def test_every_item_needs_a_description_and_a_positive_amount():
    errors = _valid(items=[("  ", Decimal("10")), ("Ok", Decimal("0"))])

    assert "Todo item precisa de uma descrição." in errors
    assert "Todo item precisa de um valor positivo." in errors


def test_the_scope_is_required():
    assert "Descreva o escopo da proposta." in _valid(scope="  ")


@pytest.mark.parametrize("days", [0, -3, 1000])
def test_the_lead_time_must_be_a_sensible_number_of_days(days):
    assert "Informe um prazo estimado entre 1 e 730 dias." in _valid(lead_time_days=days)


def test_the_validity_must_be_a_future_date():
    assert "A validade deve ser uma data futura." in _valid(valid_until=TODAY)
    assert "A validade deve ser uma data futura." in _valid(valid_until=TODAY - timedelta(days=1))
    assert _valid(valid_until=TODAY + timedelta(days=1)) == []


def test_the_validity_cannot_be_absurdly_far():
    assert "A validade deve ser de no máximo 180 dias." in _valid(valid_until=TODAY + timedelta(days=181))


def test_a_total_above_the_limit_is_rejected():
    errors = _valid(items=[("Tudo", Decimal("99999999.99")), ("Mais", Decimal("1.00"))])

    assert "O total da proposta excede o limite permitido." in errors


def test_a_proposal_is_valid_through_its_last_day_and_expires_after_it():
    assert is_expired(TODAY, TODAY) is False
    assert is_expired(TODAY - timedelta(days=1), TODAY) is True


def checklist(**states):
    return [
        {"key": key, "state": states.get(key, "ok"), "note": ""} for key in FEASIBILITY_ITEMS
    ]


def test_the_checklist_catalog_covers_the_prd_minimum():
    assert set(FEASIBILITY_ITEMS) == {"acesso", "terreno", "escavacao", "hidraulica_eletrica", "medidas", "visita"}


def test_approval_needs_every_item_ok():
    assert validate_feasibility("approved", checklist(), "") == []
    assert validate_feasibility("approved", checklist(terreno="ressalva"), "")
    assert validate_feasibility("approved", checklist(terreno="pendente"), "")


def test_conditional_approval_allows_caveats_but_no_pending_or_blocking_item():
    assert validate_feasibility("conditionally_approved", checklist(terreno="ressalva"), "") == []
    assert validate_feasibility("conditionally_approved", checklist(terreno="pendente"), "")
    assert validate_feasibility("conditionally_approved", checklist(acesso="impeditivo"), "")


def test_rejection_needs_an_explanation():
    assert validate_feasibility("rejected", checklist(acesso="impeditivo"), "") == ["Explique o motivo da reprovação."]
    assert validate_feasibility("rejected", checklist(acesso="impeditivo"), "Sem acesso para a escavadeira") == []


def test_pending_is_always_allowed_and_unknown_values_are_rejected():
    assert validate_feasibility("pending", checklist(terreno="pendente"), "") == []
    assert validate_feasibility("talvez", checklist(), "")
    assert validate_feasibility("approved", [{"key": "acesso", "state": "ok", "note": ""}], "")  # incomplete list
    assert validate_feasibility("approved", checklist(acesso="ótimo"), "")


@pytest.mark.parametrize("status,blocked", [
    ("approved", False), ("conditionally_approved", False), ("pending", True), ("rejected", True), (None, True),
])
def test_only_an_approved_or_conditionally_approved_viability_lets_the_buyer_accept(status, blocked):
    assert (acceptance_blocker(status) is not None) is blocked


def test_the_blocker_message_explains_why():
    assert "pendente" in acceptance_blocker("pending").lower()
    assert "reprovada" in acceptance_blocker("rejected").lower()
    assert "ainda não foi avaliada" in acceptance_blocker(None).lower()


def test_caveats_list_only_the_items_with_a_reservation_with_their_notes():
    items = checklist(terreno="ressalva", escavacao="ressalva")
    items[1]["note"] = "Terreno com leve declive"

    result = caveats(items)

    assert [c["label"] for c in result] == [FEASIBILITY_ITEMS["terreno"], FEASIBILITY_ITEMS["escavacao"]]
    assert result[0]["note"] == "Terreno com leve declive"
