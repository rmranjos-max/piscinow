from piscinow.qualification.flow import Goal, is_qualified, next_goal, resolve_budget

NO_ASKS = {}
ALL_REQUIRED = {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}


def test_a_new_conversation_starts_by_asking_the_location():
    assert next_goal({}, NO_ASKS, "nao_respondido") == Goal("ask_field", "localizacao", 1)


def test_the_goal_follows_the_first_missing_required_field_whatever_order_the_buyer_answered_in():
    values = {"prazo": "ate_90_dias", "localizacao": "Valinhos"}

    assert next_goal(values, NO_ASKS, "nao_respondido").field == "tipo_piscina"


def test_a_message_that_fills_several_fields_at_once_skips_straight_ahead():
    goal = next_goal(ALL_REQUIRED, NO_ASKS, "nao_respondido")

    assert goal == Goal("ask_field", "dimensoes", 1)


def test_after_three_unanswered_asks_of_a_required_field_the_goal_becomes_a_handoff_to_the_team():
    goal = next_goal({}, {"localizacao": 3}, "nao_respondido")

    assert goal == Goal("handoff", "localizacao")


def test_the_budget_is_asked_twice_and_the_second_ask_is_marked_as_attempt_two():
    values = {**ALL_REQUIRED, "dimensoes": "7 x 3 m"}

    first = next_goal(values, {}, "nao_respondido")
    second = next_goal(values, {"orcamento": 1}, "nao_respondido")

    assert first == Goal("ask_budget", "orcamento", 1)
    assert second == Goal("ask_budget", "orcamento", 2)


def test_after_two_budget_asks_the_budget_is_dropped_and_the_flow_moves_on():
    values = {**ALL_REQUIRED, "dimensoes": "7 x 3 m"}

    goal = next_goal(values, {"orcamento": 2}, "nao_respondido")

    assert goal == Goal("ask_field", "terreno", 1)


def test_two_unanswered_budget_asks_resolve_to_not_informed():
    assert resolve_budget({}, {"orcamento": 2}) == "nao_informado"
    assert resolve_budget({}, {"orcamento": 1}) is None
    assert resolve_budget({"orcamento": "ate_30_mil"}, {"orcamento": 2}) is None


def test_optional_fields_are_asked_only_once_so_the_buyer_is_not_interrogated():
    values = {**ALL_REQUIRED, "orcamento": "nao_informado"}

    assert next_goal(values, {"dimensoes": 1, "terreno": 1}, "nao_respondido") == Goal("ask_consent")


def test_consent_is_requested_once_the_required_fields_are_in():
    values = {**ALL_REQUIRED, "dimensoes": "7 x 3 m", "orcamento": "nao_informado", "terreno": "inclinado"}

    assert next_goal(values, NO_ASKS, "nao_respondido") == Goal("ask_consent")


def test_once_consent_is_decided_the_conversation_is_complete():
    values = {**ALL_REQUIRED, "dimensoes": "x", "orcamento": "nao_informado", "terreno": "inclinado"}

    assert next_goal(values, NO_ASKS, "concedido") == Goal("complete")
    assert next_goal(values, NO_ASKS, "recusado") == Goal("complete")


def test_an_opportunity_needs_the_required_fields_and_granted_consent():
    assert is_qualified(ALL_REQUIRED, "concedido") is True
    assert is_qualified(ALL_REQUIRED, "nao_respondido") is False
    assert is_qualified(ALL_REQUIRED, "recusado") is False
    assert is_qualified({"localizacao": "Valinhos"}, "concedido") is False


def test_a_missing_budget_never_blocks_the_opportunity():
    assert "orcamento" not in ALL_REQUIRED
    assert is_qualified(ALL_REQUIRED, "concedido") is True
