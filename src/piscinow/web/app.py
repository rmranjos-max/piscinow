import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from piscinow.agent.provider_factory import build_llm_provider
from piscinow.config import get_settings
from piscinow.payment.providers.fake_provider import FakePaymentProvider
from piscinow.rate_limit import limiter
from piscinow.web.routes import admin, chat, comprador, comprador_projeto, loja, pages, prestador, vitrine

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent

TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"))


def _format_brl(value) -> str:
    """Format a monetary value with pt-BR thousands/decimal separators, e.g. 18000 -> "18.000,00"."""
    quant = Decimal(str(value)).quantize(Decimal("0.01"))
    whole, _, frac = f"{quant:,.2f}".partition(".")
    whole = whole.replace(",", ".")
    return f"{whole},{frac}"


TEMPLATES.env.filters["brl"] = _format_brl


@asynccontextmanager
async def lifespan(app: FastAPI):
    from piscinow.agent.embeddings import embed_text

    embed_text("warmup")  # forces the model to load at startup, not on first chat message
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.session_secret == "change-me-in-production":
        logger.warning(
            "PISCINOW_SESSION_SECRET is using the insecure default value. "
            "Set a real secret before deploying to production."
        )
    app = FastAPI(title="Clube Piscinow", lifespan=lifespan)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount("/static", StaticFiles(directory=str(_HERE.parent / "static")), name="static")
    app.state.templates = TEMPLATES
    app.state.llm_provider = build_llm_provider(settings)
    app.state.payment_provider = FakePaymentProvider()
    logger.warning(
        "Pagamentos estao usando FakePaymentProvider: nenhuma cobranca ou repasse real esta "
        "sendo processado. Configure um provider real antes de ir para producao."
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(pages.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    app.include_router(loja.router)
    app.include_router(prestador.router)
    app.include_router(comprador.router)
    app.include_router(comprador_projeto.router)
    app.include_router(vitrine.router)
    return app


app = create_app()
