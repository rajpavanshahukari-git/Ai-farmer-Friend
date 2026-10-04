from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.models import DiaryEntry
from app.models.schemas import DiaryIn, DiaryOut
from app.routes.deps import current_farmer, resolve_language
from app.services import gemini_service, memory_service

router = APIRouter(prefix="/api/diary", tags=["diary"])


@router.post("")
async def add_entry(body: DiaryIn, db: Session = Depends(get_db)):
    """Voice farm diary: turn a spoken daily observation into a structured record."""
    f = current_farmer(db)
    language = resolve_language(body.language, f)
    if not body.text.strip():
        raise HTTPException(400, "text is required")
    try:
        x = await gemini_service.extract_diary(body.text, language, f.crop)
    except gemini_service.GeminiUnavailable as e:
        raise HTTPException(503, str(e))
    severity = x.severity if x.severity in ("none", "low", "medium", "high") else "low"
    entry = DiaryEntry(farmer_id=f.id, entry_date=date.today(), raw_text=body.text, language=language,
                       crop=x.crop or f.crop, observation=x.observation_en, severity=severity, tags=x.tags)
    db.add(entry)
    if severity in ("medium", "high"):
        memory_service.remember(db, f.id, [f"Diary {date.today()}: {x.observation_en} (severity {severity})"], "diary")
    db.commit()
    return {"entry": DiaryOut.model_validate(entry), "acknowledgement": x.acknowledgement}


@router.get("", response_model=list[DiaryOut])
def list_entries(limit: int = 30, db: Session = Depends(get_db)):
    f = current_farmer(db)
    return db.scalars(
        select(DiaryEntry).where(DiaryEntry.farmer_id == f.id).order_by(DiaryEntry.created_at.desc()).limit(limit)
    ).all()


@router.get("/trends")
async def trends(language: str | None = None, db: Session = Depends(get_db)):
    f = current_farmer(db)
    rows = db.scalars(
        select(DiaryEntry).where(DiaryEntry.farmer_id == f.id).order_by(DiaryEntry.created_at.desc()).limit(14)
    ).all()
    if len(rows) < 2:
        raise HTTPException(400, "Record at least two diary notes to see a trend.")
    lines = [f"{r.entry_date}: {r.observation} (severity {r.severity})" for r in reversed(rows)]
    try:
        t = await gemini_service.diary_trend(lines, resolve_language(language, f), f.crop)
    except gemini_service.GeminiUnavailable as e:
        raise HTTPException(503, str(e))
    return t.model_dump()
