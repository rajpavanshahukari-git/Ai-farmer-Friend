"""Central configuration. All secrets come from environment variables (backend/.env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODELS = [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]

MURF_API_KEY = os.getenv("MURF_API_KEY", "")
MURF_BASE_URL = "https://api.murf.ai/v1"

WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

STORAGE_DIR = BASE_DIR / "storage"
AUDIO_DIR = STORAGE_DIR / "audio"
UPLOAD_DIR = STORAGE_DIR / "uploads"
for d in (AUDIO_DIR, UPLOAD_DIR):
    d.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{STORAGE_DIR / 'farmer.db'}"
if DATABASE_URL.startswith("sqlite:///./"):
    DATABASE_URL = f"sqlite:///{BASE_DIR / DATABASE_URL.removeprefix('sqlite:///./')}"
# Render/Neon/Heroku hand out postgres:// URLs; SQLAlchemy needs the psycopg (v3) driver named explicitly
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix(prefix)

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
# Netlify production + deploy-preview URLs (https://<site>.netlify.app, https://deploy-preview-1--<site>.netlify.app)
CORS_ORIGIN_REGEX = os.getenv("CORS_ORIGIN_REGEX", r"https://([a-z0-9-]+--)?[a-z0-9-]+\.netlify\.app")

# Languages supported end to end. Add a row here (plus UI strings in the frontend) to add a language.
LANGUAGES = {
    "en-IN": {"name": "English", "native": "English"},
    "te-IN": {"name": "Telugu", "native": "తెలుగు"},
    "hi-IN": {"name": "Hindi", "native": "हिन्दी"},
}
DEFAULT_LANGUAGE = "te-IN"
