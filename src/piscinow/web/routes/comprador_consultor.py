from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.agent.llm_provider import LLMProvider
from piscinow.agent.memory_store import MemoryStore
from piscinow.comprador_auth import require_comprador
from piscinow.models.conversation import MessageRole
from piscinow.models.member import Member, ProfileType
from piscinow.models.qualification import ConsentState, FieldSource
from piscinow.qualification.agent import ConsultorAgent
from piscinow.qualification.fields import FIELDS, REQUIRED
from piscinow.qualification.service import (
    conversation_of,
    get_or_create_qualification,
    known_fields,
    refresh_status,
    set_consent,
    set_field,
)
from piscinow.rate_limit import chat_rate_limit_string, limiter
from piscinow.web.deps import get_db, get_llm_provider

router = APIRouter(prefix="/comprador/consultor")

MAX_MESSAGE_CHARS = 1000
BACK = "/comprador/consultor"


def _knowledge_for(db: Session):
    def lookup(text: str) -> list[str]:
        items = MemoryStore(db).search(query=text, profile_type=ProfileType.COMPRADOR, limit=4)
        return [item.content for item in items]

    return lookup


def _missing_required(values: dict) -> list[str]:
    return [FIELDS[key].label for key in REQUIRED if key not in values]


@router.get("", response_class=HTMLResponse)
async def consultor(
    request: Request,
    aviso: str | None = None,
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    qualification = get_or_create_qualification(db, comprador)
    conversation = conversation_of(db, qualification)
    values = qualification.values()
    messages = [
        {"from_agent": m.role == MessageRole.AGENT, "text": m.content} for m in conversation.messages
    ]
    return request.app.state.templates.TemplateResponse(
        request,
        "comprador_consultor.html",
        {
            "messages": messages,
            "briefing": known_fields(qualification),
            "missing": _missing_required(values),
            "consent": qualification.consent.value,
            "attention": qualification.attention_at is not None,
            "unavailable": aviso == "indisponivel",
        },
    )


@router.post("/mensagem")
@limiter.limit(chat_rate_limit_string)
async def enviar_mensagem(
    request: Request,
    message: str = Form(...),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    comprador: Member = Depends(require_comprador),
):
    text = message.strip()
    if not text:
        return RedirectResponse(url=f"{BACK}#responder", status_code=303)
    qualification = get_or_create_qualification(db, comprador)
    agent = ConsultorAgent(db, llm, knowledge=_knowledge_for(db))
    turn = await agent.handle_message(qualification, text[:MAX_MESSAGE_CHARS])
    suffix = "?aviso=indisponivel" if turn.unavailable else ""
    return RedirectResponse(url=f"{BACK}{suffix}#responder", status_code=303)


@router.post("/campo")
async def corrigir_campo(
    key: str = Form(...),
    value: str = Form(...),
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    if key not in FIELDS:
        raise HTTPException(status_code=404)
    qualification = get_or_create_qualification(db, comprador)
    if not set_field(
        db, qualification, key, value, source=FieldSource.CLIENTE, actor=f"comprador:{comprador.id}"
    ):
        raise HTTPException(status_code=400, detail="Valor inválido para este campo.")
    refresh_status(db, qualification)
    return RedirectResponse(url=BACK, status_code=303)


@router.post("/consentimento")
async def consentimento(
    decisao: str = Form(...),
    db: Session = Depends(get_db),
    comprador: Member = Depends(require_comprador),
):
    if decisao not in ("autorizo", "depois"):
        raise HTTPException(status_code=400)
    qualification = get_or_create_qualification(db, comprador)
    granted = decisao == "autorizo"
    if granted and _missing_required(qualification.values()):
        raise HTTPException(status_code=400, detail="Faltam dados essenciais para compartilhar o briefing.")
    set_consent(db, qualification, granted)
    return RedirectResponse(url=BACK, status_code=303)
