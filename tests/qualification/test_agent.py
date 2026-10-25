import json

import pytest

from piscinow.agent.providers.fake_provider import FakeLLMProvider
from piscinow.models.conversation import MessageRole
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.models.qualification import ConsentState, FieldSource
from piscinow.qualification.agent import ConsultorAgent
from piscinow.qualification.guardrails import SAFE_FALLBACK
from piscinow.qualification.service import conversation_of, get_or_create_qualification, set_field


class RecordingLLM(FakeLLMProvider):
    """Scripted provider that also remembers every system prompt it was given."""

    def __init__(self, scripted_responses=None):
        super().__init__(scripted_responses)
        self.systems: list[str] = []

    async def stream(self, messages, system):
        self.systems.append(system)
        async for chunk in super().stream(messages, system):
            yield chunk


class BrokenLLM(FakeLLMProvider):
    async def stream(self, messages, system):
        raise RuntimeError("provider down")
        yield ""  # pragma: no cover


def extraction(campos=None, duvida=None) -> str:
    return json.dumps({"campos": campos or {}, "duvida_para_equipe": duvida}, ensure_ascii=False)


def _comprador(db_session, name="Marina Duarte"):
    member = Member(profile_type=ProfileType.COMPRADOR, name=name, status=MemberStatus.APPROVED)
    db_session.add(member)
    db_session.flush()
    return member


def _agent(db_session, llm, knowledge=None):
    return ConsultorAgent(db_session, llm, knowledge=knowledge)


def _agent_messages(db_session, qualification):
    conversation = conversation_of(db_session, qualification)
    return [m for m in conversation.messages if m.role == MessageRole.AGENT]


def test_a_new_qualification_opens_with_a_greeting_that_says_it_is_a_virtual_assistant(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))

    [greeting] = _agent_messages(db_session, qualification)
    assert greeting.content.startswith("Oi, Marina!")
    assert "assistente virtual" in greeting.content
    assert qualification.asks == {"localizacao": 1}


@pytest.mark.asyncio
async def test_one_message_can_fill_several_fields_and_they_are_stored_as_declared_by_the_buyer(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([
        extraction({"localizacao": "Valinhos", "tipo_piscina": "Fibra", "prazo": "até 90 dias"}),
        "Que bom! Fibra em Valinhos é uma ótima combinação. Você já tem uma ideia do tamanho?",
    ])

    turn = await _agent(db_session, llm).handle_message(qualification, "Fibra em Valinhos, para os próximos 3 meses")

    assert qualification.values() == {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias"}
    assert {f.source for f in qualification.fields} == {FieldSource.CLIENTE}
    assert turn.reply.startswith("Que bom!")


@pytest.mark.asyncio
async def test_a_value_the_model_invents_outside_the_catalog_is_discarded(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([extraction({"tipo_piscina": "cristal líquido", "foo": "bar"}), "Entendi! E em que cidade?"])

    await _agent(db_session, llm).handle_message(qualification, "quero uma piscina diferente")

    assert qualification.values() == {}


@pytest.mark.asyncio
async def test_the_user_and_agent_messages_are_saved_in_order(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([extraction(), "Sem problema, me conta mais."])

    await _agent(db_session, llm).handle_message(qualification, "olá")

    roles = [m.role for m in conversation_of(db_session, qualification).messages]
    assert roles == [MessageRole.AGENT, MessageRole.USER, MessageRole.AGENT]


@pytest.mark.asyncio
async def test_each_ask_is_counted_and_a_required_field_asked_three_times_goes_to_the_team(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))  # localizacao asked once
    llm = FakeLLMProvider([extraction(), "Pode me dizer a cidade?", extraction(), "Só a cidade mesmo, por favor."])
    agent = _agent(db_session, llm)

    await agent.handle_message(qualification, "quero cotar")
    await agent.handle_message(qualification, "sei lá")

    assert qualification.asks["localizacao"] == 3
    assert qualification.attention_at is None

    llm.queue_response(extraction())
    llm.queue_response("Vou pedir para alguém da equipe te ajudar a completar isso.")
    await agent.handle_message(qualification, "ainda não sei")

    assert qualification.attention_at is not None
    assert "Localização" in qualification.attention_note


@pytest.mark.asyncio
async def test_the_budget_is_asked_twice_and_then_recorded_as_not_informed(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    for key, value in {"localizacao": "Valinhos", "tipo_piscina": "fibra", "prazo": "ate_90_dias", "dimensoes": "6x3"}.items():
        set_field(db_session, qualification, key, value, source=FieldSource.CLIENTE, actor="t")
    qualification.asks = {"localizacao": 1, "tipo_piscina": 1, "prazo": 1, "dimensoes": 1}
    llm = RecordingLLM([
        extraction(), "Para indicar as lojas certas, você já pensou numa faixa de investimento?",
        extraction(), "Entendo! Uma faixa, mesmo aproximada, ajuda as lojas a já virem com opções que cabem no seu bolso.",
        extraction(), "Tudo bem, seguimos sem isso.",
    ])
    agent = _agent(db_session, llm)

    await agent.handle_message(qualification, "tá")
    assert "orcamento" not in qualification.values()
    await agent.handle_message(qualification, "prefiro não dizer")
    assert qualification.asks["orcamento"] == 2
    assert "orcamento" not in qualification.values()
    await agent.handle_message(qualification, "não sei")

    assert qualification.values()["orcamento"] == "nao_informado"
    assert "segunda vez" in llm.systems[3]


@pytest.mark.asyncio
async def test_asking_for_the_budget_never_says_prices_will_rise(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([
        extraction(), "Aproveite, os preços vão subir no mês que vem!",
        "Os preços vão subir logo, garanto.",
        "Informar uma faixa ajuda as lojas a já virem com opções adequadas. Em que cidade fica o terreno?",
    ])

    turn = await _agent(db_session, llm).handle_message(qualification, "oi")

    assert "subir" not in turn.reply
    assert "faixa" in turn.reply


@pytest.mark.asyncio
async def test_a_reply_that_keeps_breaking_the_rules_is_replaced_by_the_safe_text_and_flags_the_team(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([extraction(), "Custa R$ 45.000.", "Fica por R$ 45.000, garanto.", "R$ 45.000 e pronto."])

    turn = await _agent(db_session, llm).handle_message(qualification, "quanto custa uma piscina de fibra?")

    assert turn.reply == SAFE_FALLBACK
    assert turn.used_fallback is True
    assert qualification.attention_at is not None
    assert _agent_messages(db_session, qualification)[-1].content == SAFE_FALLBACK


@pytest.mark.asyncio
async def test_the_agent_may_repeat_a_value_the_buyer_wrote_themselves(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([extraction(), "Com R$ 40 mil já dá para pensar em boas opções. Em que cidade?"])

    turn = await _agent(db_session, llm).handle_message(qualification, "tenho uns R$ 40 mil")

    assert turn.used_fallback is False


@pytest.mark.asyncio
async def test_the_agent_never_claims_to_be_human(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([
        extraction(), "Sou uma pessoa de verdade, pode confiar!",
        "Sou uma assistente virtual da Piscinow, uma inteligência artificial, mas estou aqui para te ajudar de verdade.",
    ])

    turn = await _agent(db_session, llm).handle_message(qualification, "você é gente ou robô?")

    assert "assistente virtual" in turn.reply
    assert turn.used_fallback is False


@pytest.mark.asyncio
async def test_a_question_the_agent_cannot_answer_opens_an_attention_request(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([
        extraction(duvida="Quer saber o prazo de entrega de uma piscina de vinil"),
        "Essa informação eu vou confirmar com a equipe e já te retorno. Em que cidade fica o terreno?",
    ])

    await _agent(db_session, llm).handle_message(qualification, "em quanto tempo entregam uma de vinil?")

    assert "prazo de entrega" in qualification.attention_note


@pytest.mark.asyncio
async def test_consent_is_never_deduced_from_the_text_or_from_the_model_output(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))
    llm = FakeLLMProvider([
        json.dumps({"campos": {"localizacao": "Valinhos", "consentimento": "concedido"}, "consent": True}),
        "Ótimo! Vamos seguir.",
    ])

    await _agent(db_session, llm).handle_message(qualification, "pode compartilhar tudo com as lojas, autorizo")

    assert qualification.consent == ConsentState.NAO_RESPONDIDO


@pytest.mark.asyncio
async def test_when_the_provider_fails_the_message_is_kept_and_nothing_is_invented(db_session):
    qualification = get_or_create_qualification(db_session, _comprador(db_session))

    turn = await _agent(db_session, BrokenLLM()).handle_message(qualification, "Fibra em Valinhos")

    assert turn.unavailable is True
    assert turn.reply is None
    conversation = conversation_of(db_session, qualification)
    assert [m.content for m in conversation.messages if m.role == MessageRole.USER] == ["Fibra em Valinhos"]
    assert len(_agent_messages(db_session, qualification)) == 1  # only the greeting


@pytest.mark.asyncio
async def test_the_prompt_carries_only_this_buyers_data_and_the_approved_knowledge(db_session):
    first = get_or_create_qualification(db_session, _comprador(db_session, "Marina Duarte"))
    set_field(db_session, first, "localizacao", "Valinhos", source=FieldSource.CLIENTE, actor="t")
    second = get_or_create_qualification(db_session, _comprador(db_session, "Carlos Pereira"))
    llm = RecordingLLM([extraction(), "Claro! Em que cidade fica o terreno?"])
    knowledge = lambda text: ["O Clube só trabalha com lojas aprovadas pela equipe."]

    await _agent(db_session, llm, knowledge=knowledge).handle_message(second, "como funciona o clube?")

    reply_prompt = llm.systems[1]
    assert "assistente virtual" in reply_prompt
    assert "lojas aprovadas pela equipe" in reply_prompt
    assert "Valinhos" not in reply_prompt
    assert "Marina" not in reply_prompt
