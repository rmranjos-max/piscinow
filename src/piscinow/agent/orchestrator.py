from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from piscinow.agent.handlers.base import ConversationHandler
from piscinow.agent.handlers.comprador import CompradorHandler
from piscinow.agent.handlers.embaixador import EmbaixadorHandler
from piscinow.agent.handlers.loja import LojaHandler
from piscinow.agent.handlers.prestador import PrestadorHandler
from piscinow.agent.llm_provider import ChatMessage, LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.router import Router
from piscinow.config import get_settings
from piscinow.models.conversation import Conversation, Message, MessageRole
from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.referral import get_or_create_referral_code

HANDLER_CLASSES: dict[ProfileType, type[ConversationHandler]] = {
    ProfileType.COMPRADOR: CompradorHandler,
    ProfileType.LOJA: LojaHandler,
    ProfileType.PRESTADOR: PrestadorHandler,
    ProfileType.EMBAIXADOR: EmbaixadorHandler,
}

CLARIFYING_QUESTION = (
    "Voce e comprador, loja, prestador de servico ou quer ser embaixador do Clube?"
)


@dataclass
class TurnResult:
    reply_text: str
    finalized: bool
    newly_finalized: bool


class Orchestrator:
    def __init__(self, session: Session, llm: LLMProvider):
        self._session = session
        self._llm = llm
        self._memory = MemoryStore(session)
        self._router = Router(llm)
        self._settings = get_settings()

    async def handle_user_message(
        self, conversation: Conversation, message_text: str, *, referred_by: Member | None
    ) -> TurnResult:
        self._session.add(Message(conversation=conversation, role=MessageRole.USER, content=message_text))
        self._session.flush()

        if conversation.member_id is not None:
            reply_text = "Sua conversa ja foi concluida; nossa equipe segue o atendimento a partir daqui."
            self._session.add(Message(conversation=conversation, role=MessageRole.AGENT, content=reply_text))
            return TurnResult(reply_text=reply_text, finalized=True, newly_finalized=False)

        history = self._history_as_messages(conversation)

        if conversation.profile_type_detected is None:
            classification = await self._router.classify(message_text)
            if classification.profile_type is None:
                self._session.add(
                    Message(conversation=conversation, role=MessageRole.AGENT, content=CLARIFYING_QUESTION)
                )
                return TurnResult(reply_text=CLARIFYING_QUESTION, finalized=False, newly_finalized=False)
            conversation.profile_type_detected = classification.profile_type

        handler = HANDLER_CLASSES[conversation.profile_type_detected](self._llm, self._memory)
        conversation.collected_fields = await handler.extract_fields(history, conversation.collected_fields)

        if handler.missing_fields(conversation.collected_fields):
            reply = await handler.reply(history, conversation.collected_fields)
            self._session.add(Message(conversation=conversation, role=MessageRole.AGENT, content=reply))
            return TurnResult(reply_text=reply, finalized=False, newly_finalized=False)

        member = self._finalize_member(conversation, referred_by=referred_by)
        reply = self._finalize_reply(member)
        self._session.add(Message(conversation=conversation, role=MessageRole.AGENT, content=reply))
        conversation.ended_at = conversation.ended_at or datetime.now(timezone.utc)
        return TurnResult(reply_text=reply, finalized=True, newly_finalized=True)

    def _finalize_member(self, conversation: Conversation, *, referred_by: Member | None) -> Member:
        fields = conversation.collected_fields
        member = Member(
            profile_type=conversation.profile_type_detected,
            name=fields.get("name", ""),
            profile_details=fields,
            referred_by_member_id=referred_by.id if referred_by else None,
        )
        member.submit_for_review()
        if referred_by is not None:
            member.auto_approve_via_referral()
        self._session.add(member)
        self._session.flush()
        if member.profile_type == ProfileType.EMBAIXADOR:
            get_or_create_referral_code(self._session, member)
        conversation.member_id = member.id
        return member

    def _finalize_reply(self, member: Member) -> str:
        if member.status == MemberStatus.APPROVED:
            base = "Voce entrou direto no Clube pela indicacao recebida."
        else:
            base = "Voce esta na fila de admissao do Clube; a equipe revisa e libera o acesso."
        if member.profile_type == ProfileType.EMBAIXADOR:
            link = f"{self._settings.public_base_url}/convite/{member.referral_code}"
            return f"{base} Seu link de indicacao: {link}"
        return base

    @staticmethod
    def _history_as_messages(conversation: Conversation) -> list[ChatMessage]:
        role_map = {MessageRole.USER: "user", MessageRole.AGENT: "assistant"}
        return [ChatMessage(role=role_map[m.role], content=m.content) for m in conversation.messages]
