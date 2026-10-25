import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from piscinow.web.deps import get_db

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("readyz: banco de dados indisponivel")
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}
