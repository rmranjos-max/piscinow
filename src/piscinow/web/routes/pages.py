from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from piscinow.referral import find_referrer
from piscinow.web.deps import get_db

router = APIRouter()

REFERRAL_COOKIE = "piscinow_ref"


@router.get("/convite/{code}")
async def convite(code: str, db: Session = Depends(get_db)):
    referrer = find_referrer(db, code)
    response = RedirectResponse(url="/")
    if referrer is not None:
        response.set_cookie(
            REFERRAL_COOKIE, code, max_age=60 * 60 * 24 * 30, httponly=True, samesite="lax"
        )
    return response


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    db: Session = Depends(get_db),
    piscinow_ref: str | None = Cookie(default=None),
):
    templates = request.app.state.templates
    referrer = find_referrer(db, piscinow_ref) if piscinow_ref else None
    return templates.TemplateResponse(
        request, "home.html", {"referred_by_name": referrer.name if referrer else None}
    )
