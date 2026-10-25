import uuid

from piscinow.qualification.projection import partner_briefing

MEMBER_ID = uuid.UUID("a7f2c0de-0000-4000-8000-000000000001")
VALUES = {
    "localizacao": "Valinhos",
    "tipo_piscina": "fibra",
    "dimensoes": "7 x 3 m",
    "prazo": "ate_90_dias",
    "orcamento": "nao_informado",
    "terreno": "plano_acesso_livre",
}


def test_the_briefing_uses_human_labels_in_a_fixed_order():
    briefing = partner_briefing(MEMBER_ID, VALUES)

    assert [item["rotulo"] for item in briefing["campos"]] == [
        "Localização", "Tipo de piscina", "Dimensões", "Prazo desejado", "Orçamento", "Terreno",
    ]
    assert {item["rotulo"]: item["valor"] for item in briefing["campos"]}["Prazo desejado"] == "Até 90 dias"


def test_the_buyer_is_identified_only_by_a_stable_anonymous_code():
    first = partner_briefing(MEMBER_ID, VALUES)["codigo"]
    again = partner_briefing(MEMBER_ID, VALUES)["codigo"]
    other = partner_briefing(uuid.uuid4(), VALUES)["codigo"]

    assert first == again
    assert first != other
    assert first.startswith("Cliente #") and str(MEMBER_ID) not in first


def test_the_projection_contains_no_name_phone_or_email_even_if_they_leak_into_the_values():
    leaky = {**VALUES, "nome": "Marina Duarte", "email": "marina@example.com", "telefone": "19 90000-0000"}

    text = repr(partner_briefing(MEMBER_ID, leaky))

    for secret in ["Marina", "marina@example.com", "90000-0000"]:
        assert secret not in text


def test_fields_without_a_value_are_simply_left_out():
    briefing = partner_briefing(MEMBER_ID, {"localizacao": "Valinhos"})

    assert [item["rotulo"] for item in briefing["campos"]] == ["Localização"]
