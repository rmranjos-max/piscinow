from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from piscinow.media.storage import LocalMediaStorage

router = APIRouter()


@router.get("/midia/{key:path}")
async def midia(key: str, request: Request):
    """Serve photos kept on local disk (development). With a bucket, photos come from its own address."""
    storage = request.app.state.media_storage
    if not isinstance(storage, LocalMediaStorage):
        raise HTTPException(status_code=404)
    path = storage.path_for(key)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404)
    # Every stored file is a JPEG we encoded ourselves; say so and forbid the browser from guessing.
    return FileResponse(
        path, media_type="image/jpeg",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=31536000, immutable"},
    )
