from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from piscinow.models.admin import AdminUser
from piscinow.web.deps import get_db

ADMIN_SESSION_KEY = "admin_user_id"


def login(request: Request, db: Session, email: str, password: str) -> bool:
    admin = db.scalar(select(AdminUser).where(AdminUser.email == email))
    if admin is None or not admin.verify_password(password):
        return False
    request.session[ADMIN_SESSION_KEY] = str(admin.id)
    return True


def logout(request: Request) -> None:
    request.session.pop(ADMIN_SESSION_KEY, None)


def require_admin(request: Request, db: Session = Depends(get_db)) -> AdminUser:
    admin_id = request.session.get(ADMIN_SESSION_KEY)
    if not admin_id:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    admin = db.get(AdminUser, admin_id)
    if admin is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/admin/login"})
    return admin
