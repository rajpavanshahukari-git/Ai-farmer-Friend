"""Crop calendars: stage timelines (days after sowing) and stage-specific tasks.

Durations are typical for Andhra Pradesh / Telangana conditions and vary by variety and season;
they are used for reminders and as context, not as exact agronomic advice.
"""
from datetime import date, timedelta

# (stage, start_day, end_day, tasks[(category, title, every_n_days)])
CALENDARS: dict[str, list[tuple]] = {
    "paddy": [
        ("Nursery", 0, 25, [("water", "Keep nursery bed moist, avoid standing water", 3), ("pest", "Check seedlings for leaf damage", 5)]),
        ("Transplantation", 25, 35, [("water", "Maintain 2-3 cm water after transplanting", 2), ("monitoring", "Fill gaps where seedlings died", 7)]),
        ("Vegetative stage", 35, 75, [("pest", "Inspect for stem borer and leaf folder", 7), ("water", "Keep 3-5 cm water; alternate wetting and drying", 3), ("monitoring", "Check leaf colour for nitrogen need", 10)]),
        ("Flowering", 75, 100, [("water", "Do not let field dry during flowering", 2), ("pest", "Inspect for brown planthopper at plant base", 5)]),
        ("Grain filling", 100, 125, [("monitoring", "Watch for neck blast and grain discolouration", 5), ("water", "Keep light moisture", 4)]),
        ("Harvest", 125, 140, [("water", "Drain field 10 days before harvest", 30), ("harvest", "Prepare harvesting and drying space", 30)]),
    ],
    "chilli": [
        ("Nursery", 0, 40, [("pest", "Check nursery for damping-off and sucking pests", 5), ("water", "Light irrigation of nursery bed", 3)]),
        ("Transplantation", 40, 50, [("water", "Irrigate right after transplanting", 3), ("monitoring", "Replace dead seedlings", 7)]),
        ("Vegetative stage", 50, 90, [("pest", "Check leaf undersides for thrips, mites and whitefly", 5), ("irrigation", "Check soil moisture before irrigating", 4), ("monitoring", "Look for leaf curl", 7)]),
        ("Flowering", 90, 120, [("pest", "Inspect flowers and buds for thrips", 4), ("irrigation", "Avoid water stress - flowers drop", 3)]),
        ("Fruiting", 120, 180, [("pest", "Check fruits for borers and fruit rot", 5), ("irrigation", "Regular light irrigation", 4)]),
        ("Harvest", 180, 240, [("harvest", "Pick ripe red fruits and dry on clean tarpaulin", 7)]),
    ],
    "cotton": [
        ("Sowing & emergence", 0, 20, [("monitoring", "Check germination and gap fill", 5)]),
        ("Vegetative stage", 20, 60, [("pest", "Check for sucking pests (jassids, aphids, whitefly)", 5), ("irrigation", "Check soil moisture", 5)]),
        ("Squaring", 60, 90, [("pest", "Inspect squares for pink bollworm", 5)]),
        ("Flowering & boll formation", 90, 140, [("pest", "Check rosette flowers and bolls for pink bollworm", 4), ("irrigation", "Avoid water stress", 4)]),
        ("Boll opening & harvest", 140, 180, [("harvest", "Pick open bolls, keep cotton clean and dry", 7)]),
    ],
    "tomato": [
        ("Nursery", 0, 25, [("pest", "Check nursery for damping-off", 4)]),
        ("Transplantation", 25, 35, [("water", "Irrigate after transplanting", 2)]),
        ("Vegetative stage", 35, 60, [("pest", "Check for leaf miner and whitefly", 5), ("monitoring", "Stake plants", 10)]),
        ("Flowering & fruiting", 60, 95, [("pest", "Inspect fruits for borer", 4), ("monitoring", "Watch leaves for early blight spots", 5)]),
        ("Harvest", 95, 140, [("harvest", "Harvest at breaker stage every few days", 3)]),
    ],
    "maize": [
        ("Emergence", 0, 15, [("monitoring", "Check germination", 5)]),
        ("Vegetative stage", 15, 50, [("pest", "Check whorls for fall armyworm", 4), ("irrigation", "Check soil moisture", 5)]),
        ("Tasseling & silking", 50, 75, [("irrigation", "Critical stage - do not let crop face water stress", 3)]),
        ("Grain filling", 75, 100, [("monitoring", "Check cobs for damage", 7)]),
        ("Harvest", 100, 115, [("harvest", "Harvest when husks dry and grains hard", 30)]),
    ],
    "groundnut": [
        ("Emergence", 0, 15, [("monitoring", "Check germination", 5)]),
        ("Vegetative stage", 15, 35, [("pest", "Check for leaf miner and thrips", 5)]),
        ("Pegging & flowering", 35, 70, [("irrigation", "Keep soil moist and loose for pegging", 4)]),
        ("Pod development", 70, 100, [("pest", "Check for tikka leaf spot", 5), ("irrigation", "Avoid water stress", 4)]),
        ("Harvest", 100, 120, [("harvest", "Check pod maturity before harvest", 7)]),
    ],
}

ALIASES = {"rice": "paddy", "vari": "paddy", "mirchi": "chilli", "mirapa": "chilli", "chili": "chilli", "pathi": "cotton", "corn": "maize", "verusenaga": "groundnut", "peanut": "groundnut"}


def _key(crop: str) -> str | None:
    c = (crop or "").strip().lower()
    c = ALIASES.get(c, c)
    return c if c in CALENDARS else None


def crop_calendar(crop: str, sowing_date: date | None, override_stage: str = "") -> dict:
    key = _key(crop)
    if not key:
        return {"crop": crop, "supported": False, "stages": [], "current_stage": override_stage or None, "days_after_sowing": None}
    das = (date.today() - sowing_date).days if sowing_date else None
    stages = []
    current = None
    for name, start, end, _tasks in CALENDARS[key]:
        status = "unknown"
        if das is not None:
            status = "done" if das >= end else "current" if das >= start else "upcoming"
            if status == "current":
                current = name
        stages.append({
            "name": name, "start_day": start, "end_day": end, "status": status,
            "start_date": (sowing_date + timedelta(days=start)).isoformat() if sowing_date else None,
        })
    if das is not None and current is None and das >= 0:
        current = stages[-1]["name"] if das >= stages[-1]["end_day"] else stages[0]["name"]
    if override_stage:
        current = override_stage
    next_stage = None
    for i, s in enumerate(stages):
        if s["name"] == current and i + 1 < len(stages):
            next_stage = stages[i + 1]
    return {"crop": key, "supported": True, "stages": stages, "current_stage": current,
            "next_stage": next_stage, "days_after_sowing": das}


def suggested_tasks(crop: str, stage: str | None, horizon_days: int = 14) -> list[dict]:
    key = _key(crop)
    if not key or not stage:
        return []
    for name, _s, _e, tasks in CALENDARS[key]:
        if name == stage:
            out = []
            for category, title, every in tasks:
                d = 0
                while d < horizon_days:
                    out.append({"category": category, "title": title, "due_date": (date.today() + timedelta(days=d)).isoformat()})
                    d += every
            return sorted(out, key=lambda t: t["due_date"])
    return []
