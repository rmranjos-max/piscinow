from decimal import Decimal

from piscinow.web.journey import comprador_journey, stage_overview


def _states(journey):
    return [step["state"] for step in journey["steps"]]


def test_a_new_comprador_is_told_to_choose_a_product():
    journey = comprador_journey(has_product=False, confirmed=False, payment_status=None, all_released=False)

    assert _states(journey) == ["current", "", "", ""]
    assert journey["next"]["href"] == "/vitrine/produtos"


def test_a_draft_with_a_product_is_told_to_review_and_confirm():
    journey = comprador_journey(has_product=True, confirmed=False, payment_status=None, all_released=False)

    assert _states(journey) == ["done", "current", "", ""]
    assert journey["next"]["href"] == "/comprador/projeto"


def test_a_confirmed_project_waits_for_the_team_to_build_the_schedule():
    journey = comprador_journey(has_product=True, confirmed=True, payment_status=None, all_released=False)

    assert _states(journey) == ["done", "done", "current", ""]
    assert journey["next"]["href"] is None
    assert "cronograma" in journey["next"]["text"].lower()


def test_a_pending_payment_points_to_the_payment_page():
    journey = comprador_journey(has_product=True, confirmed=True, payment_status="pendente", all_released=False)

    assert _states(journey) == ["done", "done", "current", ""]
    assert journey["next"]["href"] == "/comprador/projeto/pagamento"


def test_a_paid_project_points_to_the_stage_tracking():
    journey = comprador_journey(has_product=True, confirmed=True, payment_status="pago", all_released=False)

    assert _states(journey) == ["done", "done", "done", "current"]
    assert journey["next"]["href"] == "/comprador/obra"


def test_when_every_stage_is_released_the_whole_journey_is_done():
    journey = comprador_journey(has_product=True, confirmed=True, payment_status="pago", all_released=True)

    assert _states(journey) == ["done", "done", "done", "done"]


ROWS = [
    ("estrutura", "retido", Decimal("18000.00"), "Studio Fibra Sul"),
    ("acabamento", "liberado", Decimal("3000.00"), "Instalações Sul"),
]


def test_stage_overview_always_lists_the_four_fixed_stages_in_order():
    overview = stage_overview(ROWS)

    assert [s["key"] for s in overview] == ["terraplanagem", "estrutura", "revestimento", "acabamento"]


def test_a_stage_with_no_items_says_so_instead_of_inventing_a_status():
    overview = {s["key"]: s for s in stage_overview(ROWS)}

    assert overview["terraplanagem"]["state"] == "sem"
    assert overview["terraplanagem"]["lines"] == []


def test_a_stage_is_retained_until_every_item_in_it_is_released():
    overview = {s["key"]: s for s in stage_overview(ROWS)}

    assert overview["estrutura"]["state"] == "retido"
    assert overview["estrutura"]["total"] == Decimal("18000.00")
    assert overview["acabamento"]["state"] == "liberado"


def test_a_stage_with_some_items_released_and_some_not_is_partial():
    rows = [("estrutura", "liberado", Decimal("100"), "A"), ("estrutura", "retido", Decimal("50"), "B")]

    stage = {s["key"]: s for s in stage_overview(rows)}["estrutura"]

    assert stage["state"] == "parcial"
    assert stage["total"] == Decimal("150")


def test_a_release_is_a_payout_not_a_statement_that_the_work_is_finished():
    labels = {s["state_label"] for s in stage_overview(ROWS)}

    assert "Repasse liberado" in labels
    assert not any("conclu" in label.lower() for label in labels)
