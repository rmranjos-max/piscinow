import pytest

from piscinow.web.journey import buyer_journey


def journey(**overrides):
    base = dict(
        briefing="none", deal_status=None, open_proposals=0, payment_status=None, all_released=False, project_linked=False,
    )
    return buyer_journey(**{**base, **overrides})


def states(result):
    return [step["state"] for step in result["steps"]]


def test_the_journey_always_has_the_same_five_steps():
    assert [s["label"] for s in journey()["steps"]] == ["Briefing", "Propostas", "Aceite", "Pagamento por fases", "Obra"]


def test_a_new_buyer_starts_by_talking_to_the_assistant():
    result = journey()

    assert states(result) == ["current", "", "", "", ""]
    assert result["next"]["href"] == "/comprador/consultor"
    assert result["next"]["cta"] == "Conversar com a assistente"


def test_an_unfinished_briefing_sends_the_buyer_back_to_the_conversation():
    result = journey(briefing="in_progress")

    assert result["next"]["title"] == "Termine o seu briefing"
    assert result["next"]["href"] == "/comprador/consultor"


def test_a_buyer_who_preferred_to_talk_first_can_authorize_later():
    result = journey(briefing="declined")

    assert "autoriz" in result["next"]["text"].lower()
    assert result["next"]["href"] == "/comprador/consultor"


@pytest.mark.parametrize("status", ["qualified", "matched"])
def test_while_the_team_picks_the_stores_there_is_nothing_for_the_buyer_to_do(status):
    result = journey(briefing="done", deal_status=status)

    assert states(result) == ["done", "current", "", "", ""]
    assert result["next"]["href"] is None


def test_while_the_stores_analyze_the_buyer_is_told_so_and_can_open_the_proposals_page():
    result = journey(briefing="done", deal_status="partner_review")

    assert "analisando" in result["next"]["text"]
    assert result["next"]["href"] == "/comprador/propostas"


@pytest.mark.parametrize("count,title", [(1, "Compare a proposta que chegou"), (2, "Compare as 2 propostas que chegaram")])
def test_open_proposals_are_the_next_step_with_the_right_plural(count, title):
    result = journey(briefing="done", deal_status="proposal_sent", open_proposals=count)

    assert result["next"]["title"] == title
    assert result["next"]["cta"] == "Ver as propostas"
    assert states(result) == ["done", "current", "", "", ""]


def test_after_the_acceptance_the_team_prepares_the_payment():
    result = journey(briefing="done", deal_status="accepted", project_linked=True)

    assert states(result) == ["done", "done", "done", "current", ""]
    assert result["next"]["href"] is None
    assert "pagamento por fases" in result["next"]["text"]


def test_a_pending_payment_points_to_the_payment_page():
    result = journey(briefing="done", deal_status="accepted", project_linked=True, payment_status="pendente")

    assert result["next"]["href"] == "/comprador/projeto/pagamento"


def test_a_paid_project_moves_to_the_work():
    result = journey(briefing="done", deal_status="accepted", project_linked=True, payment_status="pago")

    assert states(result) == ["done", "done", "done", "done", "current"]
    assert result["next"]["href"] == "/comprador/obra"


def test_when_every_phase_is_released_the_whole_journey_is_done():
    result = journey(briefing="done", deal_status="accepted", project_linked=True, payment_status="pago", all_released=True)

    assert states(result) == ["done"] * 5


def test_a_lost_opportunity_offers_to_talk_again():
    result = journey(briefing="done", deal_status="lost")

    assert result["next"]["href"] == "/comprador/consultor"
    assert states(result)[0] == "done"


def test_an_old_path_project_with_a_payment_still_shows_its_payment():
    result = journey(briefing="none", payment_status="pendente", project_linked=True)

    assert result["next"]["href"] == "/comprador/projeto/pagamento"
    assert states(result) == ["done", "done", "done", "current", ""]
