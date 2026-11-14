from datetime import datetime, timedelta, timezone

import pytest

from piscinow.overview.stats import average_duration, format_duration, funnel, loss_reasons

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def test_the_funnel_lists_every_state_in_pipeline_order_with_zero_for_the_missing_ones():
    rows = funnel({"qualified": 3, "proposal_sent": 1, "lost": 2})

    assert [r["key"] for r in rows] == [
        "qualified", "matched", "partner_review", "proposal_sent", "negotiating", "accepted", "lost", "cancelled",
    ]
    assert {r["key"]: r["count"] for r in rows} == {
        "qualified": 3, "matched": 0, "partner_review": 0, "proposal_sent": 1, "negotiating": 0, "accepted": 0,
        "lost": 2, "cancelled": 0,
    }
    assert rows[0]["label"] == "Qualificada"


def test_the_funnel_ignores_states_it_does_not_know_and_reports_the_share_of_the_largest_stage():
    rows = funnel({"qualified": 4, "accepted": 2, "weird": 9})

    assert all(r["key"] != "weird" for r in rows)
    assert next(r for r in rows if r["key"] == "qualified")["share"] == 100
    assert next(r for r in rows if r["key"] == "accepted")["share"] == 50


def test_an_empty_funnel_has_zero_shares_not_a_division_error():
    assert all(r["share"] == 0 and r["count"] == 0 for r in funnel({}))


def test_loss_reasons_group_by_text_ignoring_case_and_spaces_and_sort_by_frequency():
    reasons = ["Sem retorno", " sem retorno ", "Desistiu", "SEM RETORNO", "Desistiu", "Preço"]

    assert loss_reasons(reasons) == [("Sem retorno", 3), ("Desistiu", 2), ("Preço", 1)]


def test_loss_reasons_ignore_empty_values_and_respect_the_limit():
    assert loss_reasons(["", None, "  ", "A", "B", "C"], limit=2) == [("A", 1), ("B", 1)]


def test_average_duration_is_none_without_data_and_a_plain_mean_otherwise():
    assert average_duration([]) is None
    pairs = [(NOW, NOW + timedelta(days=2)), (NOW, NOW + timedelta(days=4))]

    assert average_duration(pairs) == timedelta(days=3)


def test_negative_durations_from_bad_data_are_ignored():
    assert average_duration([(NOW, NOW - timedelta(days=1))]) is None


@pytest.mark.parametrize("delta,expected", [
    (timedelta(minutes=20), "20 min"), (timedelta(hours=5, minutes=10), "5 h"), (timedelta(days=1, hours=3), "1 dia e 3 h"),
    (timedelta(days=3), "3 dias"), (timedelta(days=12, hours=7), "12 dias e 7 h"), (None, "—"),
])
def test_durations_are_shown_in_plain_portuguese(delta, expected):
    assert format_duration(delta) == expected
