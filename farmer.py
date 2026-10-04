from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.models import Alert, Conversation, DiaryEntry, MemoryFact, Reminder
from app.models.schemas import FarmerProfile
from app.routes.deps import current_farmer
from app.services import calendar_service, memory_service, weather_service

router = APIRouter(prefix="/api/farmer", tags=["farmer"])


@router.get("/profile", response_model=FarmerProfile)
def get_profile(db: Session = Depends(get_db)):
    return current_farmer(db)


@router.put("/profile", response_model=FarmerProfile)
async def update_profile(body: FarmerProfile, db: Session = Depends(get_db)):
    f = current_farmer(db)
    location_changed = (body.district, body.state, body.village) != (f.district, f.state, f.village)
    gps_unchanged = body.latitude == f.latitude and body.longitude == f.longitude
    for k, v in body.model_dump().items():
        setattr(f, k, v)
    # look up coordinates for the weather layer when the farmer typed a new place without GPS
    if location_changed and gps_unchanged:
        for place in (body.village, body.district):
            if place and (coords := await weather_service.geocode(place)):
                f.latitude, f.longitude = coords
                break
    db.commit()
    return f


@router.get("/history")
def history(limit: int = 30, saved_only: bool = False, db: Session = Depends(get_db)):
    f = current_farmer(db)
    q = select(Conversation).where(Conversation.farmer_id == f.id)
    if saved_only:
        q = q.where(Conversation.saved.is_(True))
    rows = db.scalars(q.order_by(Conversation.created_at.desc()).limit(limit)).all()
    return [
        {"id": c.id, "question": c.question, "language": c.language, "answer": c.response,
         "image_url": c.image_path, "mode": c.mode, "is_emergency": c.is_emergency,
         "saved": c.saved, "created_at": c.created_at}
        for c in rows
    ]


@router.post("/history/{conv_id}/save")
def toggle_save(conv_id: int, db: Session = Depends(get_db)):
    c = db.get(Conversation, conv_id)
    if not c or c.farmer_id != current_farmer(db).id:
        raise HTTPException(404, "Conversation not found")
    c.saved = not c.saved
    db.commit()
    return {"id": c.id, "saved": c.saved}


@router.get("/memory")
def memory(db: Session = Depends(get_db)):
    f = current_farmer(db)
    rows = db.scalars(
        select(MemoryFact).where(MemoryFact.farmer_id == f.id).order_by(MemoryFact.created_at.desc()).limit(50)
    ).all()
    return [{"id": m.id, "fact": m.fact, "source": m.source, "created_at": m.created_at} for m in rows]


@router.get("/dashboard")
async def dashboard(db: Session = Depends(get_db)):
    f = current_farmer(db)
    cal = calendar_service.crop_calendar(f.crop, f.sowing_date, f.farming_stage)
    w = await memory_service.weather_for(f)
    last_diary = db.scalars(
        select(DiaryEntry).where(DiaryEntry.farmer_id == f.id).order_by(DiaryEntry.created_at.desc()).limit(1)
    ).first()
    tasks = db.scalars(
        select(Reminder).where(Reminder.farmer_id == f.id, Reminder.done.is_(False)).order_by(Reminder.due_date).limit(5)
    ).all()
    unread = db.scalars(
        select(Alert).where(Alert.farmer_id == f.id, Alert.read.is_(False)).order_by(Alert.created_at.desc()).limit(5)
    ).all()
    return {
        "profile": FarmerProfile.model_validate(f),
        "calendar": cal,
        "weather": w,
        "crop_health": (
            {"severity": last_diary.severity, "observation": last_diary.observation,
             "note": last_diary.raw_text, "date": last_diary.entry_date}
            if last_diary else None
        ),
        "tasks": [{"id": t.id, "title": t.title, "category": t.category, "due_date": t.due_date} for t in tasks],
        "alerts": [
            {"id": a.id, "text": a.text, "priority": a.priority, "kind": a.kind,
             "audio_url": a.audio_url, "language": a.language}
            for a in unread
        ],
    }
