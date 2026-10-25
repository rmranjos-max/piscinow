import pytest

from piscinow.matching.rules import StoreProfile, city_matches, evaluate, is_effective

BUYER = {"localizacao": "Valinhos, SP", "tipo_piscina": "fibra", "prazo": "ate_90_dias", "orcamento": "30_a_50_mil"}


def profile(**overrides):
    base = dict(
        active=True, service_areas=["Valinhos", "Campinas"], pool_types=["fibra", "vinil"],
        budget_bands=["30_a_50_mil", "acima_de_50_mil"], capacity=3,
    )
    return StoreProfile(**{**base, **overrides})


def result(values=BUYER, store=None, *, approved=True, load=0):
    return evaluate(store if store is not None else profile(), approved=approved, values=values, open_load=load)


def failed(res):
    return [c["key"] for c in res.criteria if not c["passed"]]


def test_a_store_that_meets_every_criterion_is_eligible_and_all_criteria_are_recorded():
    res = result()

    assert res.eligible is True
    assert [c["key"] for c in res.criteria] == ["homologada", "perfil", "cidade", "tipo", "orcamento", "capacidade"]
    assert all(c["passed"] and c["detail"] for c in res.criteria)


def test_a_store_that_is_not_approved_is_never_eligible():
    assert failed(result(approved=False)) == ["homologada"]
    assert result(approved=False).eligible is False


def test_a_store_without_a_profile_is_ineligible_with_the_reason_recorded():
    res = evaluate(None, approved=True, values=BUYER, open_load=0)

    assert res.eligible is False
    assert failed(res)[0] == "perfil"
    assert any("sem perfil" in c["detail"].lower() for c in res.criteria)
    assert len(res.criteria) == 6


def test_an_inactive_profile_is_ineligible():
    assert failed(result(store=profile(active=False))) == ["perfil", "cidade", "tipo", "orcamento", "capacidade"]
    assert result(store=profile(active=False)).eligible is False


@pytest.mark.parametrize("location,expected", [
    ("Valinhos", True), ("valinhos, sp", True), ("Vinhedo", False), ("São Paulo", False),
    ("Campinas - SP", True), ("Valinhosa", False),
])
def test_the_city_must_appear_as_a_whole_word_ignoring_case_and_accents(location, expected):
    assert (city_matches(["Valinhos", "Campinas"], location) is not None) is expected


def test_accents_do_not_matter_in_the_city():
    assert city_matches(["São Paulo"], "sao paulo") == "São Paulo"


def test_a_buyer_outside_the_service_area_fails_only_the_city():
    assert failed(result({**BUYER, "localizacao": "Vinhedo"})) == ["cidade"]


def test_a_missing_location_fails_the_city():
    values = {k: v for k, v in BUYER.items() if k != "localizacao"}

    assert failed(result(values)) == ["cidade"]


def test_a_pool_type_the_store_does_not_build_fails():
    assert failed(result({**BUYER, "tipo_piscina": "alvenaria"})) == ["tipo"]


def test_a_buyer_who_does_not_know_the_pool_type_passes_and_the_detail_says_so():
    res = result({**BUYER, "tipo_piscina": "ainda_nao_sei"})

    assert res.eligible is True
    assert "ainda não sabe" in next(c for c in res.criteria if c["key"] == "tipo")["detail"].lower()


def test_a_budget_outside_the_store_bands_fails():
    assert failed(result({**BUYER, "orcamento": "ate_30_mil"})) == ["orcamento"]


@pytest.mark.parametrize("budget", ["nao_informado", None])
def test_an_unknown_budget_does_not_eliminate_the_store(budget):
    values = {k: v for k, v in BUYER.items() if k != "orcamento"}
    if budget:
        values["orcamento"] = budget

    assert result(values).eligible is True


def test_a_store_at_capacity_is_ineligible():
    assert failed(result(load=3)) == ["capacidade"]
    assert result(load=2).eligible is True


def test_several_failures_are_all_reported():
    res = result({**BUYER, "localizacao": "Vinhedo", "tipo_piscina": "alvenaria"})

    assert failed(res) == ["cidade", "tipo"]


@pytest.mark.parametrize("eligible,override,effective", [
    (True, "nenhum", True), (False, "nenhum", False),
    (True, "excluida", False), (False, "incluida", True),
    (True, "incluida", True), (False, "excluida", False),
])
def test_the_effective_decision_combines_the_system_result_and_the_override(eligible, override, effective):
    assert is_effective(eligible, override) is effective
