from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from piscinow.agent.llm_provider import LLMProvider
from piscinow.db import make_engine, make_session_factory

_engine = make_engine()
_SessionFactory = make_session_factory(_engine)


def get_db() -> Generator[Session, None, None]:
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_llm_provider(request: Request) -> LLMProvider:
    return request.app.state.llm_provider
