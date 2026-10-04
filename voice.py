from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config.settings import LANGUAGES
from app.database.db import get_db
from app.models.schemas import VoiceRequest, VoiceResponse
from app.routes.deps import current_farmer, resolve_language
from app.services import gemini_service, murf_service

router = APIRouter(prefix="/api/voice", tags=["voice"])


@router.post("/generate", response_model=VoiceResponse)
async def generate(body: VoiceRequest):
    if body.language not in LANGUAGES:
        raise HTTPException(400, f"Unsupported language {body.language}")
    try:
        return await murf_service.synthesize(body.text, body.language, body.voice, body.speed, body.pitch, body.purpose)
    except murf_service.MurfError as e:
        raise HTTPException(502, str(e))


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...), language: str | None = Form(None), db: Session = Depends(get_db)):
    """Speech-to-text with Gemini, for browsers without the Web Speech API (Firefox, some phones)."""
    data = await audio.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "Recording too long")
    mime = (audio.content_type or "audio/webm").split(";")[0]
    try:
        t = await gemini_service.transcribe(data, mime, resolve_language(language, current_farmer(db)))
    except gemini_service.GeminiUnavailable as e:
        raise HTTPException(503, str(e))
    return {"text": t.text, "language": t.language}


@router.get("/voices")
async def voices(language: str = "te-IN"):
    try:
        all_voices = await murf_service.list_voices()
    except murf_service.MurfError as e:
        raise HTTPException(502, str(e))
    out = []
    for v in all_voices:
        locales = murf_service._locales(v)
        if language in locales:
            out.append({
                "voice_id": v["voiceId"], "name": v["displayName"], "gender": v.get("gender"),
                "native": v["locale"] == language, "styles": locales[language].get("availableStyles", []),
            })
    out.sort(key=lambda x: (not x["native"], not x["voice_id"].split("-")[1:2] == ["IN"]))
    return out
