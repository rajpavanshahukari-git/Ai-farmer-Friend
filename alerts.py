from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import AUDIO_DIR
from app.database.db import get_db
from app.models.models import Alert
from app.models.schemas import AlertIn, AlertOut
from app.routes.deps import current_farmer, resolve_language
from app.services import gemini_service, memory_service, murf_service

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

# alert priority -> Murf voice personality
PRIORITY_PURPOSE = {"urgent": "emergency", "warning": "normal", "normal": "reminder"}


@router.get("", response_model=list[AlertOut])
def list_alerts(limit: int = 30, db: Session = Depends(get_db)):
    f = current_farmer(db)
    return db.scalars(select(Alert).where(Alert.farmer_id == f.id).order_by(Alert.created_at.desc()).limit(limit)).all()


@router.post("", response_model=list[AlertOut])
async def create_alerts(body: AlertIn, db: Session = Depends(get_db)):
    """Manual alert (text + priority), or `auto: true` to let Gemini write personalised alerts
    from the weather, crop stage and diary."""
    f = current_farmer(db)
    language = resolve_language(body.language, f)
    if body.auto:
        context = await memory_service.build_context(db, f)
        try:
            generated = await gemini_service.generate_alerts(context, language)
        except gemini_service.GeminiUnavailable as e:
            raise HTTPException(503, str(e))
        items = [(a.kind, a.priority, a.text) for a in generated.alerts]
    else:
        if not body.text:
            raise HTTPException(400, "text is required for a manual alert")
        items = [(body.kind, body.priority, body.text)]

    created = []
    for kind, priority, text in items:
        a = Alert(farmer_id=f.id, kind=kind, priority=priority if priority in PRIORITY_PURPOSE else "normal",
                  text=text, language=language)
        db.add(a)
        created.append(a)
    db.commit()
    return created


@router.post("/{aid}/audio", response_model=AlertOut)
async def alert_audio(aid: int, db: Session = Depends(get_db)):
    """Generate (or reuse) the Murf voice for an alert, voiced according to its priority."""
    f = current_farmer(db)
    a = db.get(Alert, aid)
    if not a or a.farmer_id != f.id:
        raise HTTPException(404, "Alert not found")
    cached = a.audio_url and (AUDIO_DIR / a.audio_url.rsplit("/", 1)[-1]).exists()
    if not cached:  # never generated, or the disk cache was wiped by a restart
        try:
            out = await murf_service.synthesize(a.text, a.language, f.voice_gender, f.voice_speed,
                                                purpose=PRIORITY_PURPOSE.get(a.priority, "normal"))
        except murf_service.MurfError as e:
            raise HTTPException(502, str(e))
        a.audio_url = out["audio_url"]
        db.commit()
    return a


@router.patch("/{aid}/read", response_model=AlertOut)
def mark_read(aid: int, db: Session = Depends(get_db)):
    a = db.get(Alert, aid)
    if not a or a.farmer_id != current_farmer(db).id:
        raise HTTPException(404, "Alert not found")
    a.read = True
    db.commit()
    return a
