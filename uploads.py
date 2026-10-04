from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.models import Upload
from app.routes.deps import current_farmer

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


@router.get("/{upload_id}")
def get_upload(upload_id: int, db: Session = Depends(get_db)):
    up = db.get(Upload, upload_id)
    if not up or up.farmer_id != current_farmer(db).id:
        raise HTTPException(404, "Photo not found")
    return Response(up.data, media_type=up.mime_type, headers={"Cache-Control": "private, max-age=31536000, immutable"})
