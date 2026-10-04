"""Seed the demo farmer (hackathon scenario: chilli farmer from Guntur, Telugu)."""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.models import Farmer


def seed_demo_farmer(db: Session) -> None:
    if db.get(Farmer, 1):
        return
    db.add(
        Farmer(
            id=1,
            name="Ravi",
            language="te-IN",
            state="Andhra Pradesh",
            district="Guntur",
            village="Tadikonda",
            crop="Chilli",
            crop_variety="Teja",
            land_acres=3,
            soil_type="Black soil",
            irrigation="Borewell",
            sowing_date=date.today() - timedelta(days=55),
            latitude=16.3067,
            longitude=80.4365,
        )
    )
    db.commit()
