import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Form, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from piscinow.agent.extractor import Extractor
from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.agent.orchestrator import Orchestrator
from piscinow.models.conversation import Conversation
from piscinow.rate_limit import chat_rate_limit_string, limiter
from piscinow.referral import find_referrer
from piscinow.web.deps import get_db, get_llm_provider

router = APIRouter()

logger = logging.getLogger(__name__)

SESSION_COOKIE = "piscinow_session"
REFERRAL_COOKIE = "piscinow_ref"


def _get_or_create_conversation(db: Session, session_id: str | None) -> tuple[Conversation, str]:
    if session_id:
        try:
            conversation = db.get(Conversation, uuid.UUID(session_id))
        except ValueError:
            conversation = None
        if conversation is not None:
            return conversation, session_id
    conversation = Conversation()
    db.add(conversation)
    db.flush()
    return conversation, str(conversation.id)


@router.post("/api/chat/message")
@limiter.limit(chat_rate_limit_string)
async def send_message(
    request: Request,
    background_tasks: BackgroundTasks,
    message: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    piscinow_session: str | None = Cookie(default=None),
    piscinow_ref: str | None = Cookie(default=None),
):
    conversation, session_id = _get_or_create_conversation(db, piscinow_session)

    referrer = find_referrer(db, piscinow_ref) if piscinow_ref else None
    orchestrator = Orchestrator(db, llm)

    # NOTE: delivers the full reply as soon as it's ready, not token-by-token —
    # extraction + classification must finish before the final reply is known.
    # StreamingResponse keeps the wire contract open for true token streaming later.
    async def body():
        result = await orchestrator.handle_user_message(conversation, message, referred_by=referrer)
        if result.newly_finalized:
            # Best-effort learning loop (spec: "roda ao final de cada conversa,
            # background, best-effort") — never blocks the reply.
            background_tasks.add_task(_run_extractor, db, llm, conversation)
        yield result.reply_text

    streaming_response = StreamingResponse(body(), media_type="text/plain")
    # Setting the cookie on the injected `response: Response` dependency does
    # NOT work here: FastAPI does not merge that parameter's headers into a
    # directly-returned `Response` subclass instance (verified empirically
    # against the installed FastAPI version), so the cookie must be set
    # directly on the `StreamingResponse` object that is actually returned.
    streaming_response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=60 * 60 * 2,
        httponly=True,
        samesite="lax",
        secure=request.app.state.cookie_secure,
    )
    return streaming_response


async def _run_extractor(db: Session, llm: LLMProvider, conversation: Conversation) -> None:
    # No explicit db.commit() here: `MemoryStore.write` already flushes, and
    # `get_db`'s own post-yield commit (Task 20) runs after background tasks
    # complete, persisting this write in production. Committing here would
    # also break the tests' rollback-based session isolation (Task 2's
    # `db_session` fixture), since in tests `db` is that same fixture session.
    extractor = Extractor(llm, MemoryStore(db))
    try:
        await extractor.process(conversation)
    except Exception:
        # Never let an extractor failure propagate into get_db's dependency
        # cleanup (which would rollback the already-streamed reply's writes).
        logger.exception("Extractor.process failed for conversation %s", conversation.id)
