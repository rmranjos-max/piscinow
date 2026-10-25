from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class OriginCheckMiddleware:
    """Rejects state-changing requests whose Origin (or Referer, when Origin is
    absent) is not this site. Browsers always send Origin on cross-site POSTs, so
    a forged form on another domain cannot pass; requests carrying neither header
    (tests, curl) are not browser-driven CSRF and are let through."""

    def __init__(self, app, extra_hosts=()):
        self.app = app
        self.extra_hosts = {h.lower() for h in extra_hosts if h}

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            if not self._is_allowed(Headers(scope=scope)):
                response = PlainTextResponse("Origem da requisicao nao permitida.", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def _is_allowed(self, headers: Headers) -> bool:
        allowed = {h for h in {headers.get("host", "").lower(), *self.extra_hosts} if h}
        origin = headers.get("origin")
        if origin is not None:
            return origin != "null" and urlsplit(origin).netloc.lower() in allowed
        referer = headers.get("referer")
        if referer:
            return urlsplit(referer).netloc.lower() in allowed
        return True
