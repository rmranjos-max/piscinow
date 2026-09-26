from slowapi import Limiter
from slowapi.util import get_remote_address

from piscinow.config import get_settings

limiter = Limiter(key_func=get_remote_address)


def chat_rate_limit_string() -> str:
    settings = get_settings()
    return f"{settings.chat_rate_limit_per_minute}/minute"


def admin_login_rate_limit_string() -> str:
    return "5/minute"


def loja_login_rate_limit_string() -> str:
    return "5/minute"


def prestador_login_rate_limit_string() -> str:
    return "5/minute"


def comprador_login_rate_limit_string() -> str:
    return "5/minute"
