from starlette.datastructures import MutableHeaders

SENSITIVE_PATH_MARKER = "/definir-senha/"


class SensitivePathHeadersMiddleware:
    """The set-password token travels in the URL. On those pages, stop the browser from
    sending the URL as Referer to anything the page loads, and from caching the page."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or SENSITIVE_PATH_MARKER not in scope["path"]:
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_headers)
