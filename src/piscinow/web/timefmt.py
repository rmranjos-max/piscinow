from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Everything is stored in UTC; people read it in Brasília time.
BRASILIA = ZoneInfo("America/Sao_Paulo")


def to_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(BRASILIA)


def local(value: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Jinja filter: a stored datetime as Brasília wall-clock text, or an em dash."""
    converted = to_local(value)
    return converted.strftime(fmt) if converted else "—"
