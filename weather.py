from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.routes.deps import current_farmer
from app.services import weather_service

router = APIRouter(prefix="/api", tags=["weather"])


@router.get("/weather")
async def weather(lat: float | None = None, lon: float | None = None, db: Session = Depends(get_db)):
    if lat is None or lon is None:
        f = current_farmer(db)
        lat, lon = f.latitude, f.longitude
    if lat is None or lon is None:
        raise HTTPException(400, "No location. Allow location access or set your district in the profile.")
    try:
        return await weather_service.get_weather(lat, lon)
    except Exception as e:
        raise HTTPException(502, f"Weather service unavailable: {e}")
