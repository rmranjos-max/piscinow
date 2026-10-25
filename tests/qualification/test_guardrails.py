import pytest

from piscinow.qualification.guardrails import SAFE_FALLBACK, check_reply

USER = ["Quero uma piscina de fibra em Valinhos, uns 30 mil de orçamento"]


def test_a_warm_reply_with_no_commitments_passes():
    reply = "Que legal, Valinhos é uma ótima região! Me conta: pretende ter a piscina pronta em quanto tempo?"

    assert check_reply(reply, USER) == []


def test_echoing_a_value_the_buyer_wrote_is_allowed():
    assert check_reply("Entendi, algo em torno de R$ 30 mil, certo?", USER) == []


def test_inventing_a_price_is_blocked():
    assert "valor_nao_informado" in check_reply("Uma piscina de fibra sai por R$ 18.000.", USER)
    assert "valor_nao_informado" in check_reply("Fica em torno de 25 mil reais.", USER)


def test_the_fixed_budget_range_labels_may_be_offered_as_suggestions():
    reply = "Costumo ver faixas como até R$ 30 mil, de R$ 30 a 50 mil ou acima de R$ 50 mil. Alguma te serve?"

    assert check_reply(reply, ["quero uma piscina"]) == []


@pytest.mark.parametrize(
    "reply",
    [
        "Eu garanto que fica pronta em 60 dias.",
        "Prometo o melhor preço da região.",
        "Temos garantia de 10 anos nesse modelo.",
        "O prazo de entrega de 45 dias está confirmado.",
    ],
)
def test_promises_of_deadline_or_warranty_are_blocked(reply):
    assert "promessa" in check_reply(reply, USER)


@pytest.mark.parametrize("reply", ["Aproveite, os preços vão subir no mês que vem!", "O preço tende a aumentar em breve."])
def test_claims_about_future_prices_are_blocked(reply):
    assert "preco_futuro" in check_reply(reply, USER)


@pytest.mark.parametrize(
    "reply",
    ["Sou uma pessoa da equipe, pode confiar.", "Não sou um robô, sou atendente.", "Sou humano e estou aqui para ajudar."],
)
def test_claiming_to_be_human_is_blocked(reply):
    assert "afirma_ser_humano" in check_reply(reply, USER)


def test_saying_it_is_an_assistant_is_fine():
    assert check_reply("Sou a assistente virtual da Piscinow e vou te ajudar com o projeto.", USER) == []


def test_claims_about_stock_or_availability_are_blocked():
    assert "disponibilidade" in check_reply("Esse modelo está em estoque, pronta entrega.", USER)


def test_the_safe_fallback_text_itself_passes_every_check():
    assert check_reply(SAFE_FALLBACK, []) == []
