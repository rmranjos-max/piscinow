import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

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
from piscinow.web.navigation import shell_context
from piscinow.web.origin_check import OriginCheckMiddleware
from piscinow.web.sensitive_headers import SensitivePathHeadersMiddleware
from piscinow.web.routes import (
    admin,
    chat,
    comprador,
    comprador_consultor,
    comprador_projeto,
    galeria,
    health,
    loja,
    pages,
    prestador,
    vitrine,
)

logger = logging.getLogger(__name__)

INSECURE_SESSION_SECRET = "change-me-in-production"

_HERE = Path(__file__).resolve().parent

TEMPLATES = Jinja2Templates(directory=str(_HERE / "templates"), context_processors=[shell_context])


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
    # No-op under pytest/uvicorn when the root logger already has handlers.
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    is_production = settings.environment == "production"
    if settings.session_secret == INSECURE_SESSION_SECRET:
        if is_production:
            raise RuntimeError(
                "PISCINOW_SESSION_SECRET esta com o valor padrao inseguro. "
                "Defina um segredo real antes de subir em producao."
            )
        logger.warning(
            "PISCINOW_SESSION_SECRET is using the insecure default value. "
            "Set a real secret before deploying to production."
        )
    app = FastAPI(title="Clube Piscinow", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        https_only=is_production,
        same_site="lax",
        max_age=settings.session_max_age_seconds,
    )
    app.add_middleware(OriginCheckMiddleware, extra_hosts=[urlsplit(settings.public_base_url).netloc])
    app.add_middleware(SensitivePathHeadersMiddleware)
    app.state.cookie_secure = is_production
    app.state.environment = settings.environment
    app.mount("/static", StaticFiles(directory=str(_HERE.parent / "static")), name="static")
    app.state.templates = TEMPLATES
    app.state.llm_provider = build_llm_provider(settings)
    payment_provider = FakePaymentProvider()
    app.state.payment_provider = payment_provider
    app.state.payments_simulated = payment_provider.is_simulation
    app.state.payments_enabled = (
        not payment_provider.is_simulation or not is_production or settings.allow_payment_simulation
    )
    if payment_provider.is_simulation and is_production and settings.allow_payment_simulation:
        logger.error(
            "Producao com PISCINOW_ALLOW_PAYMENT_SIMULATION ligado: pagamentos sao SIMULADOS, "
            "nenhuma cobranca ou repasse real esta sendo processado."
        )
    elif payment_provider.is_simulation and is_production:
        logger.warning(
            "Pagamentos desligados em producao: o provider atual e uma simulacao. "
            "Configure um provider real para habilitar pagar e liberar fases."
        )
    elif payment_provider.is_simulation:
        logger.warning("Pagamentos em modo de simulacao: nenhuma cobranca ou repasse real.")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(health.router)
    if not is_production:
        app.include_router(galeria.router)
    app.include_router(pages.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    app.include_router(loja.router)
    app.include_router(prestador.router)
    app.include_router(comprador.router)
    app.include_router(comprador_projeto.router)
    app.include_router(comprador_consultor.router)
    app.include_router(vitrine.router)
    return app


app = create_app()
