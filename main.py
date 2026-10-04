"""AI Voice Farmer Assistant - FastAPI entry point.

Run from backend/:  .venv/Scripts/uvicorn app.main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config.settings import (
    BASE_DIR, CORS_ORIGIN_REGEX, CORS_ORIGINS, GEMINI_API_KEY, LANGUAGES, MURF_API_KEY, STORAGE_DIR,
)
from app.database.db import init_db
from app.routes import alerts, chat, diary, farmer, reminders, uploads, voice, weather
from app.utils.rate_limit import RateLimitMiddleware

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AI Voice Farmer Assistant", version="1.0.0", lifespan=lifespan)
app.add_middleware(RateLimitMiddleware)
# The Netlify frontend calls this API directly (see frontend/src/services/api.js VITE_API_BASE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX or None,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (chat, voice, farmer, weather, reminders, alerts, diary, uploads):
    app.include_router(r.router)

# generated Murf audio (a disk cache - safe to lose on Render restarts; it is regenerated on demand)
app.mount("/media", StaticFiles(directory=STORAGE_DIR), name="media")


@app.get("/api/health")
def health():
    return {"ok": True, "gemini": bool(GEMINI_API_KEY), "murf": bool(MURF_API_KEY), "languages": LANGUAGES}


# Serve the built React app (frontend/dist) in production
dist = BASE_DIR.parent / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
