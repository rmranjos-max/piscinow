import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from piscinow.agent.json_extraction import parse_json_object
from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.models.conversation import Message, MessageRole
from piscinow.models.member import Member
from piscinow.models.qualification import FieldSource, LeadQualification
from piscinow.qualification.fields import FIELDS, label_for
from piscinow.qualification.flow import Goal, next_goal, resolve_budget
from piscinow.qualification.guardrails import SAFE_FALLBACK, check_reply
from piscinow.qualification.service import (
    conversation_of,
    count_ask,
    refresh_status,
    request_attention,
    set_field,
)

logger = logging.getLogger(__name__)

MAX_REGENERATIONS = 2
EXTRACTION_HISTORY = 10
REPLY_HISTORY = 24
MAX_REPLY_CHARS = 1200

Knowledge = Callable[[str], list[str]]


@dataclass
class AgentTurn:
    reply: str | None
    unavailable: bool = False
    used_fallback: bool = False


PERSONA = """Você é a assistente virtual da Piscinow, um clube fechado que aproxima quem quer uma piscina de lojas e instaladores aprovados pela equipe.
Converse como uma consultora de vendas atenciosa: calorosa, natural, em português do Brasil, com mensagens curtas (no máximo 3 frases), uma pergunta por vez, sem listas, sem títulos e sem formatação.
Se a pessoa tiver dúvida ou resistência, acolha, responda de forma breve e só depois retome a conversa.

Transparência: você é uma assistente virtual (inteligência artificial). Se perguntarem, diga isso com naturalidade e sem constrangimento. Nunca diga nem sugira que é uma pessoa.

Você NUNCA:
- cita valores em reais que a pessoa não escreveu (a única exceção são as faixas de orçamento sugeridas abaixo);
- afirma preço, prazo de entrega, disponibilidade, estoque, garantia ou condição de pagamento;
- diz ou insinua que os preços vão subir, mudar ou que existe uma promoção por tempo limitado;
- pede nome completo, telefone, e-mail, CPF ou qualquer dado de pagamento;
- considera consentimento dado por texto: o consentimento só vale quando a pessoa usa o botão.
Quando não souber, ou quando a pergunta for sobre preço, prazo, pagamento ou liberação de dinheiro, diga que vai confirmar com a equipe e retome a conversa."""


def _choices_text(key: str) -> str:
    choices = FIELDS[key].choices
    return ", ".join(f'"{value}" ({label})' for value, label in choices.items()) if choices else "texto curto"


def _extraction_system() -> str:
    lines = "\n".join(f'- "{key}": {definition.label}; valores aceitos: {_choices_text(key)}' for key, definition in FIELDS.items())
    return (
        "Você extrai dados de uma conversa sobre a compra de uma piscina. Leia a ÚLTIMA mensagem da pessoa "
        "(use as anteriores só para entender o contexto) e devolva APENAS um JSON no formato "
        '{"campos": {...}, "duvida_para_equipe": null}.\n'
        f"Campos possíveis:\n{lines}\n"
        "Inclua em \"campos\" somente o que a pessoa disse de forma explícita; use exatamente os valores aceitos "
        "quando houver lista. Se ela mudar de ideia, devolva o valor novo. Não deduza nem invente.\n"
        "Em \"duvida_para_equipe\" resuma, em uma frase, qualquer pergunta que exija confirmação humana "
        "(preço, prazo de entrega, pagamento, liberação de dinheiro, garantia, disponibilidade); "
        "caso contrário, null."
    )


def _goal_text(goal: Goal) -> str:
    if goal.kind == "ask_field":
        definition = FIELDS[goal.field]
        options = f" Opções: {_choices_text(goal.field)}." if definition.choices else ""
        again = (
            " Você já perguntou isso e a pessoa não respondeu; pergunte de outro jeito, mais simples, sem insistir."
            if goal.attempt and goal.attempt > 1 else ""
        )
        return f"Descubra, de forma natural: {definition.label.lower()}.{options}{again}"
    if goal.kind == "ask_budget":
        ranges = "até R$ 30 mil, de R$ 30 a 50 mil ou acima de R$ 50 mil"
        if goal.attempt == 1:
            return (
                "Pergunte se a pessoa já pensou numa faixa de investimento, explicando que isso serve para "
                f"indicar lojas com opções adequadas. Faixas sugeridas: {ranges}."
            )
        return (
            "Esta é a segunda vez que você pergunta o orçamento. Reforce o valor de informar uma faixa: as lojas "
            "já chegam com opções que cabem no bolso, e a pessoa economiza tempo. NÃO diga que preços vão subir ou "
            f"mudar. Diga que, se preferir, pode seguir sem informar. Faixas sugeridas: {ranges}."
        )
    if goal.kind == "ask_consent":
        return (
            "Os dados principais estão completos. Explique que, com a autorização da pessoa, o briefing (sem nome "
            "e sem contato) será compartilhado com lojas compatíveis, e que ela pode autorizar pelos botões da tela "
            "ou preferir continuar conversando antes. Não peça para ela digitar a autorização."
        )
    if goal.kind == "handoff":
        return (
            "A pessoa não conseguiu informar um dado essencial. Diga com gentileza que vai pedir para a equipe da "
            "Piscinow ajudar a completar o briefing, e que ela pode seguir conversando."
        )
    return (
        "O briefing está completo. Responda dúvidas e explique que a equipe e as lojas compatíveis seguem pela "
        "plataforma. Não prometa prazo nem valor."
    )


def _reply_system(qualification: LeadQualification, goal: Goal, knowledge: list[str], first_name: str) -> str:
    collected = "\n".join(
        f"- {FIELDS[f.key].label}: {label_for(f.key, f.value)}" for f in qualification.fields if f.key in FIELDS
    ) or "nada ainda"
    approved = "\n".join(f"- {item}" for item in knowledge) or "nenhum item relevante"
    name = f"A pessoa se chama {first_name}.\n" if first_name else ""
    return (
        f"{PERSONA}\n\n{name}Dados já informados pela pessoa:\n{collected}\n\n"
        f"Conhecimento aprovado pela equipe (use só isto para fatos sobre o Clube):\n{approved}\n\n"
        f"Objetivo desta resposta: {_goal_text(goal)}"
    )


def _recent(history: list[ChatMessage], limit: int) -> list[ChatMessage]:
    """The last messages, never starting with the assistant (providers require a user turn first)."""
    window = history[-limit:]
    while window and window[0].role != "user":
        window = window[1:]
    return window


class ConsultorAgent:
    """Free-form sales conversation. Code picks the goal and validates every field; the model only words things."""

    def __init__(self, db: Session, llm: LLMProvider, knowledge: Knowledge | None = None):
        self._db = db
        self._llm = llm
        self._knowledge = knowledge

    async def handle_message(self, qualification: LeadQualification, text: str) -> AgentTurn:
        conversation = conversation_of(self._db, qualification)
        self._db.add(Message(conversation=conversation, role=MessageRole.USER, content=text))
        self._db.flush()
        self._db.refresh(conversation)

        history = [
            ChatMessage(role="user" if m.role == MessageRole.USER else "assistant", content=m.content)
            for m in conversation.messages
        ]
        user_texts = [m.content for m in conversation.messages if m.role == MessageRole.USER]
        actor = f"comprador:{qualification.member_id}"

        try:
            await self._absorb(qualification, _recent(history, EXTRACTION_HISTORY), actor)
            goal = self._decide(qualification)
            reply, used_fallback = await self._write_reply(
                qualification, goal, _recent(history, REPLY_HISTORY), user_texts, text
            )
        except Exception:
            logger.exception("Consultor turn failed for qualification %s", qualification.id)
            return AgentTurn(reply=None, unavailable=True)

        if used_fallback:
            request_attention(qualification, f"Resposta segura usada na mensagem: {text[:150]}")
        elif goal.kind in ("ask_field", "ask_budget"):
            count_ask(qualification, goal.field)
        if goal.kind == "handoff":
            request_attention(
                qualification,
                f"Sem resposta após {self._asks(qualification, goal.field)} perguntas: {FIELDS[goal.field].label}",
            )

        self._db.add(Message(conversation=conversation, role=MessageRole.AGENT, content=reply))
        refresh_status(self._db, qualification)
        return AgentTurn(reply=reply, used_fallback=used_fallback)

    @staticmethod
    def _asks(qualification: LeadQualification, key: str) -> int:
        return (qualification.asks or {}).get(key, 0)

    async def _absorb(self, qualification: LeadQualification, history: list[ChatMessage], actor: str) -> None:
        raw = await self._llm.generate(history, system=_extraction_system())
        data = parse_json_object(raw)
        campos = data.get("campos")
        if isinstance(campos, dict):
            for key, value in campos.items():
                if key in FIELDS:
                    set_field(self._db, qualification, key, value, source=FieldSource.CLIENTE, actor=actor)
        duvida = data.get("duvida_para_equipe")
        if isinstance(duvida, str) and duvida.strip():
            request_attention(qualification, f"Dúvida do comprador: {duvida.strip()}")

    def _decide(self, qualification: LeadQualification) -> Goal:
        values = qualification.values()
        asks = qualification.asks or {}
        if resolve_budget(values, asks):
            set_field(
                self._db, qualification, "orcamento", resolve_budget(values, asks),
                source=FieldSource.CLIENTE, actor=f"comprador:{qualification.member_id}",
            )
            values = qualification.values()
        return next_goal(values, asks, qualification.consent.value)

    async def _write_reply(
        self, qualification: LeadQualification, goal: Goal, history: list[ChatMessage],
        user_texts: list[str], last_text: str,
    ) -> tuple[str, bool]:
        knowledge = self._knowledge(last_text) if self._knowledge else []
        member = self._db.get(Member, qualification.member_id)
        first_name = (member.name or "").split()[0] if member and (member.name or "").strip() else ""
        system = _reply_system(qualification, goal, knowledge, first_name)

        for _ in range(MAX_REGENERATIONS + 1):
            reply = (await self._llm.generate(history, system=system)).strip()
            problems = check_reply(reply, user_texts) if reply else ["vazia"]
            if len(reply) > MAX_REPLY_CHARS:
                problems.append("longa")
            if not problems:
                return reply, False
            system += (
                f"\n\nSua resposta anterior foi rejeitada ({', '.join(problems)}). "
                "Reescreva sem cometer esse problema, mantendo o objetivo."
            )
        return SAFE_FALLBACK, True
