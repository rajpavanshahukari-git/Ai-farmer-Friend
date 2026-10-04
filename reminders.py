from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.models import Reminder
from app.models.schemas import ReminderIn, ReminderOut
from app.routes.deps import current_farmer, resolve_language
from app.services import calendar_service, gemini_service

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(include_done: bool = False, db: Session = Depends(get_db)):
    f = current_farmer(db)
    q = select(Reminder).where(Reminder.farmer_id == f.id)
    if not include_done:
        q = q.where(Reminder.done.is_(False))
    return db.scalars(q.order_by(Reminder.due_date)).all()


@router.post("/reminders", response_model=ReminderOut)
def create_reminder(body: ReminderIn, db: Session = Depends(get_db)):
    r = Reminder(farmer_id=current_farmer(db).id, **body.model_dump())
    db.add(r)
    db.commit()
    return r


@router.post("/reminders/auto", response_model=list[ReminderOut])
async def auto_reminders(language: str | None = None, db: Session = Depends(get_db)):
    """Create the next two weeks of tasks from the crop calendar, in the farmer's language
    (skips ones that already exist)."""
    f = current_farmer(db)
    cal = calendar_service.crop_calendar(f.crop, f.sowing_date, f.farming_stage)
    tasks = calendar_service.suggested_tasks(f.crop, cal["current_stage"])
    titles = sorted({t["title"] for t in tasks})
    translated = dict(zip(titles, await gemini_service.translate_lines(titles, resolve_language(language, f))))
    existing = {(r.title, r.due_date) for r in db.scalars(select(Reminder).where(Reminder.farmer_id == f.id))}
    created = []
    for t in tasks:
        due = date.fromisoformat(t["due_date"])
        title = translated.get(t["title"], t["title"])
        if (title, due) not in existing:
            r = Reminder(farmer_id=f.id, title=title, category=t["category"], due_date=due)
            db.add(r)
            created.append(r)
    db.commit()
    return created


@router.patch("/reminders/{rid}", response_model=ReminderOut)
def toggle_done(rid: int, db: Session = Depends(get_db)):
    r = db.get(Reminder, rid)
    if not r or r.farmer_id != current_farmer(db).id:
        raise HTTPException(404, "Reminder not found")
    r.done = not r.done
    db.commit()
    return r


@router.delete("/reminders/{rid}")
def delete_reminder(rid: int, db: Session = Depends(get_db)):
    r = db.get(Reminder, rid)
    if not r or r.farmer_id != current_farmer(db).id:
        raise HTTPException(404, "Reminder not found")
    db.delete(r)
    db.commit()
    return {"ok": True}


@router.get("/calendar")
def calendar(db: Session = Depends(get_db)):
    f = current_farmer(db)
    cal = calendar_service.crop_calendar(f.crop, f.sowing_date, f.farming_stage)
    cal["suggested_tasks"] = calendar_service.suggested_tasks(f.crop, cal["current_stage"], horizon_days=7)
    return cal
