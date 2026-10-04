"""Murf AI text-to-speech. Server-side only - the API key never reaches the browser.

Voice selection:
  1. explicit Murf voiceId, if the caller passes one
  2. preferred voice for (language, gender) from VOICE_PREFERENCES
  3. any voice whose native locale matches, then any multilingual voice that supports the locale
Murf has no native Telugu voice yet, so Telugu uses multilingual voices with `multiNativeLocale=te-IN`.

Personality: the purpose (normal / emergency / reminder / educational) picks the speaking style
and adjusts the rate, so an urgent alert sounds different from a calm reminder.
"""
import asyncio
import base64
import hashlib
import json
import logging

import httpx

from app.config.settings import AUDIO_DIR, MURF_API_KEY, MURF_BASE_URL
from app.utils.speech import prepare_for_speech, split_for_tts

log = logging.getLogger(__name__)

VOICE_PREFERENCES = {
    ("en-IN", "female"): ["en-IN-isha", "en-IN-priya"],
    ("en-IN", "male"): ["en-IN-rohan", "en-IN-eashwar"],
    ("hi-IN", "female"): ["hi-IN-shweta", "hi-IN-ayushi"],
    ("hi-IN", "male"): ["hi-IN-shaan", "hi-IN-kabir"],
    ("te-IN", "female"): ["ta-IN-iniya", "bn-IN-anwesha"],
    ("te-IN", "male"): [],  # resolved dynamically from multilingual voices
}

PURPOSE_STYLE = {
    "normal": (["Conversational"], 0),
    "emergency": (["Promo", "Conversational"], 6),  # clear, energetic, slightly faster
    "reminder": (["Calm", "Conversational"], -8),
    "educational": (["Narration", "Conversational"], -5),
}

_voices: list[dict] | None = None


class MurfError(RuntimeError):
    pass


async def list_voices() -> list[dict]:
    global _voices
    if _voices is None:
        if not MURF_API_KEY:
            raise MurfError("MURF_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(f"{MURF_BASE_URL}/speech/voices", headers={"api-key": MURF_API_KEY})
        if r.status_code != 200:
            raise MurfError(f"Murf voices failed: {r.status_code} {r.text[:200]}")
        _voices = r.json()
    return _voices


def _locales(v: dict) -> dict:
    return v.get("supportedLocales") or {v["locale"]: {"availableStyles": v.get("availableStyles", [])}}


async def pick_voice(language: str, voice: str | None) -> tuple[dict, bool]:
    """Return (voice dict, needs multiNativeLocale)."""
    voices = await list_voices()
    by_id = {v["voiceId"]: v for v in voices}
    if voice and voice in by_id:
        v = by_id[voice]
        return v, v["locale"] != language
    gender = (voice or "female").lower()
    gender = gender if gender in ("male", "female") else "female"

    for vid in VOICE_PREFERENCES.get((language, gender), []):
        if vid in by_id and language in _locales(by_id[vid]):
            return by_id[vid], by_id[vid]["locale"] != language

    def g(v):
        return v.get("gender", "").lower() == gender

    native = [v for v in voices if v["locale"] == language]
    multi = [v for v in voices if v["locale"] != language and language in _locales(v)]
    # prefer Indian-accent multilingual voices for Indian languages
    multi.sort(key=lambda v: (not v["locale"].endswith("-IN"),))
    for pool, needs_locale in ((native, False), (multi, True)):
        for v in sorted(pool, key=lambda v: not g(v)):
            return v, needs_locale
    raise MurfError(f"No Murf voice available for {language}")


def _style_for(v: dict, language: str, purpose: str) -> str | None:
    available = _locales(v).get(language, {}).get("availableStyles") or v.get("availableStyles") or []
    for style in PURPOSE_STYLE.get(purpose, PURPOSE_STYLE["normal"])[0]:
        if style in available:
            return style
    return available[0] if available else None


async def _generate_chunk(client: httpx.AsyncClient, payload: dict) -> bytes:
    last = None
    for attempt in range(3):
        try:
            r = await client.post(
                f"{MURF_BASE_URL}/speech/generate",
                headers={"api-key": MURF_API_KEY, "Content-Type": "application/json"},
                json=payload,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("encodedAudio"):
                    return base64.b64decode(data["encodedAudio"])
                audio = await client.get(data["audioFile"])
                audio.raise_for_status()
                return audio.content
            last = f"{r.status_code} {r.text[:300]}"
            if r.status_code < 500 and r.status_code != 429:
                break  # bad request - retrying will not help
        except httpx.TimeoutException as e:
            last = f"timeout {e}"
        await asyncio.sleep(1.5 * (attempt + 1))
    raise MurfError(f"Murf generate failed: {last}")


async def synthesize(text: str, language: str = "te-IN", voice: str | None = None, speed: float = 1.0,
                     pitch: int = 0, purpose: str = "normal") -> dict:
    """Generate speech and return {audio_url, voice_id, style, cached}. Audio is cached on disk by content hash."""
    if not MURF_API_KEY:
        raise MurfError("MURF_API_KEY is not configured")
    speech = prepare_for_speech(text)
    if not speech:
        raise MurfError("Nothing to speak")

    v, needs_locale = await pick_voice(language, voice)
    style = _style_for(v, language, purpose)
    rate = max(-50, min(50, round((speed - 1.0) * 100) + PURPOSE_STYLE.get(purpose, PURPOSE_STYLE["normal"])[1]))
    pitch = max(-50, min(50, int(pitch)))

    base = {"voiceId": v["voiceId"], "format": "MP3", "sampleRate": 24000, "rate": rate, "pitch": pitch,
            "encodeAsBase64": True}
    if style:
        base["style"] = style
    if needs_locale:
        base["multiNativeLocale"] = language

    key = hashlib.sha256(json.dumps({**base, "text": speech}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:32]
    path = AUDIO_DIR / f"{key}.mp3"
    result = {"audio_url": f"/media/audio/{key}.mp3", "voice_id": v["voiceId"], "style": style}
    if path.exists():
        return {**result, "cached": True}

    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
        chunks = [await _generate_chunk(client, {**base, "text": part}) for part in split_for_tts(speech)]
    path.write_bytes(b"".join(chunks))  # MP3 frames concatenate cleanly
    return {**result, "cached": False}
