from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

PRESTADOR_SESSION_KEY = "prestador_member_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    member = db.scalar(
        select(Member).where(
            Member.email == email.strip().lower(),
            Member.profile_type == ProfileType.PRESTADOR,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.verify_password(password):
        return False
    request.session[PRESTADOR_SESSION_KEY] = str(member.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(PRESTADOR_SESSION_KEY, None)


def require_prestador(request: Request, db: Session = Depends(get_db)) -> Member:
    member_id = request.session.get(PRESTADOR_SESSION_KEY)
    if not member_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/prestador/login"})
    member = db.get(Member, member_id)
    if member is None or member.profile_type != ProfileType.PRESTADOR or member.status != MemberStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/prestador/login"})
    return member
