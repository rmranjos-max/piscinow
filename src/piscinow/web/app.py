from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from piscinow.agent.provider_factory import build_llm_provider
from piscinow.config import get_settings
from piscinow.rate_limit import limiter
from piscinow.web.routes import admin, chat, pages

TEMPLATES = Jinja2Templates(directory="src/piscinow/web/templates")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Clube Piscinow")
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
    app.mount("/static", StaticFiles(directory="src/piscinow/static"), name="static")
    app.state.templates = TEMPLATES
    app.state.llm_provider = build_llm_provider(settings)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(pages.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app


app = create_app()
