import secrets
import string

from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member

_ALPHABET = string.ascii_uppercase + string.digits


def generate_referral_code(*, length: int = 8) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def get_or_create_referral_code(session: Session, member: Member) -> str:
    if member.referral_code:
        return member.referral_code
    code = generate_referral_code()
    while session.scalar(select(Member).where(Member.referral_code == code)) is not None:
        code = generate_referral_code()
    member.referral_code = code
    session.flush()
    return member.referral_code


def find_referrer(session: Session, code: str) -> Member | None:
    return session.scalar(select(Member).where(Member.referral_code == code))
