from datetime import datetime, timezone

from piscinow.web.timefmt import local


def test_utc_is_shown_in_brasilia_time():
    assert local(datetime(2026, 11, 18, 21, 30, tzinfo=timezone.utc)) == "18/11/2026 18:30"


def test_a_late_utc_time_can_still_be_the_previous_day_in_brasilia():
    assert local(datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc), "%d/%m/%Y") == "18/11/2026"


def test_a_naive_value_is_treated_as_utc_and_none_becomes_a_dash():
    assert local(datetime(2026, 11, 18, 12, 0)) == "18/11/2026 09:00"
    assert local(None) == "—"
