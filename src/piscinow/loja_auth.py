from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.member import Member, MemberStatus, ProfileType
from piscinow.web.deps import get_db

LOJA_SESSION_KEY = "loja_member_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    member = db.scalar(
        select(Member).where(
            Member.email == email,
            Member.profile_type == ProfileType.LOJA,
            Member.status == MemberStatus.APPROVED,
        )
    )
    if member is None or not member.verify_password(password):
        return False
    request.session[LOJA_SESSION_KEY] = str(member.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(LOJA_SESSION_KEY, None)


def require_loja(request: Request, db: Session = Depends(get_db)) -> Member:
    member_id = request.session.get(LOJA_SESSION_KEY)
    if not member_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/loja/login"})
    member = db.get(Member, member_id)
    if member is None or member.profile_type != ProfileType.LOJA or member.status != MemberStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/loja/login"})
    return member
