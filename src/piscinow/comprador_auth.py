from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

COMPRADOR_SESSION_KEY = "comprador_member_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    member = db.scalar(
        select(Member).where(
            Member.email == email.strip().lower(),
            Member.profile_type == ProfileType.COMPRADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.verify_password(password):
        return False
    request.session[COMPRADOR_SESSION_KEY] = str(member.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(COMPRADOR_SESSION_KEY, None)


def require_comprador(request: Request, db: Session = Depends(get_db)) -> Member:
    member_id = request.session.get(COMPRADOR_SESSION_KEY)
    if not member_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/comprador/login"})
    member = db.get(Member, member_id)
    if member is None or member.profile_type != ProfileType.COMPRADOR or member.status != MemberStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/comprador/login"})
    return member
