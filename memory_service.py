"""Farmer knowledge memory: builds the context Gemini sees, and stores what it learns."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Conversation, DiaryEntry, Farmer, MemoryFact, Reminder
from app.services import calendar_service, weather_service


def profile_text(f: Farmer, stage: str | None, das: int | None) -> str:
    parts = [
        f"Name: {f.name or 'unknown'}",
        f"Location: {', '.join(p for p in (f.village, f.district, f.state) if p) or 'unknown'}",
        f"Crop: {f.crop or 'unknown'}" + (f" (variety {f.crop_variety})" if f.crop_variety else ""),
        f"Land: {f.land_acres} acres" if f.land_acres else "Land: unknown",
        f"Soil: {f.soil_type or 'unknown'}",
        f"Irrigation: {f.irrigation or 'unknown'}",
        f"Sowing date: {f.sowing_date or 'unknown'}" + (f" ({das} days ago)" if das is not None else ""),
        f"Current crop stage: {stage or 'unknown'}",
    ]
    return "\n".join(parts)


async def weather_for(f: Farmer) -> dict | None:
    if f.latitude is None or f.longitude is None:
        return None
    try:
        return await weather_service.get_weather(f.latitude, f.longitude)
    except Exception:
        return None


async def build_context(db: Session, f: Farmer, include_weather: bool = True) -> str:
    cal = calendar_service.crop_calendar(f.crop, f.sowing_date, f.farming_stage)
    sections = [f"Today: {datetime.now():%Y-%m-%d}", "FARMER PROFILE", profile_text(f, cal["current_stage"], cal["days_after_sowing"])]

    if include_weather:
        w = await weather_for(f)
        sections += ["LOCAL WEATHER", weather_service.weather_brief(w) if w else "Weather data not available."]

    facts = db.scalars(
        select(MemoryFact).where(MemoryFact.farmer_id == f.id).order_by(MemoryFact.created_at.desc()).limit(15)
    ).all()
    if facts:
        sections += ["REMEMBERED FACTS (newest first)"] + [f"- [{m.created_at:%Y-%m-%d}] {m.fact}" for m in facts]

    convs = db.scalars(
        select(Conversation).where(Conversation.farmer_id == f.id).order_by(Conversation.created_at.desc()).limit(6)
    ).all()
    if convs:
        sections += ["RECENT CONVERSATIONS (newest first)"] + [f"- [{c.created_at:%Y-%m-%d}] {c.summary}" for c in convs]

    saved = db.scalars(
        select(Conversation).where(Conversation.farmer_id == f.id, Conversation.saved.is_(True))
        .order_by(Conversation.created_at.desc()).limit(5)
    ).all()
    if saved:
        sections += ["RECOMMENDATIONS THE FARMER SAVED"] + [f"- [{c.created_at:%Y-%m-%d}] {c.summary}" for c in saved]

    diary = db.scalars(
        select(DiaryEntry).where(DiaryEntry.farmer_id == f.id).order_by(DiaryEntry.entry_date.desc()).limit(5)
    ).all()
    if diary:
        sections += ["FARM DIARY (newest first)"] + [f"- [{d.entry_date}] {d.observation} (severity {d.severity})" for d in diary]

    pending = db.scalars(
        select(Reminder).where(Reminder.farmer_id == f.id, Reminder.done.is_(False)).order_by(Reminder.due_date).limit(5)
    ).all()
    if pending:
        sections += ["UPCOMING TASKS"] + [f"- {r.due_date}: {r.title}" for r in pending]

    return "\n".join(sections)


def remember(db: Session, farmer_id: int, facts: list[str], source: str = "chat") -> None:
    for fact in facts[:5]:
        fact = fact.strip()
        if fact:
            db.add(MemoryFact(farmer_id=farmer_id, fact=fact, source=source))
