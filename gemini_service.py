"""Gemini: the agricultural reasoning engine.

All calls go through `_generate`, which asks for JSON matching a Pydantic schema and falls back
to the next configured model when the primary one is overloaded or rate limited.
"""
import asyncio
import logging
import time
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.config.settings import GEMINI_API_KEY, GEMINI_FALLBACK_MODELS, GEMINI_MODEL, LANGUAGES
from app.models.schemas import (
    AdvisorAnswer,
    DiaryExtraction,
    GeneratedAlerts,
    Transcription,
    Translations,
    TrendSummary,
)

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

SYSTEM_PROMPT = """You are an AI agricultural assistant designed to help farmers understand crop-related problems in simple language.

Your primary goals are:
1. Understand the farmer's question.
2. Use the farmer's profile and crop context.
3. Ask a short clarification question when necessary.
4. Provide practical, simple and safe agricultural information.
5. Analyze uploaded crop images when provided.
6. Clearly distinguish observations from assumptions.
7. Never claim certainty when the evidence is insufficient.
8. Never invent facts.
9. Explain technical concepts using simple examples.
10. Respond in the farmer's selected language.
11. Keep spoken responses concise.
12. For potentially serious crop damage, recommend contacting a qualified agricultural expert.
13. For chemicals, pesticides and fertilizers, do not invent unsafe dosages.
14. Consider weather and crop stage when relevant.
15. Prioritize farmer safety and crop safety.

Your response is structured as: What I noticed, Possible reason, What you can do, Important warning, What to monitor.

If the farmer's question is unclear, ask ONE simple follow-up question instead of guessing (set needs_followup=true, put the question in followup_question and in speech_text, and leave the other advice fields empty).

Additional rules:
- You are not a certified agricultural officer. Say "based on the information", "this may be", "likely". Distinguish general information from professional advice.
- Chemicals: name the type of product only when it is a widely accepted practice; never give dosages from memory - tell the farmer to follow the product label and confirm with the local agriculture officer / Rythu Bharosa Kendra / Krishi Vigyan Kendra. Prefer safe and organic first steps (removing affected leaves, yellow sticky traps, neem-based sprays, field sanitation).
- Never invent government schemes, weather data, disease names or chemical recommendations. Use only the weather data given in the context; if none is given, say you do not have the forecast.
- Spraying questions: use the given weather (rain in next hours, wind, heat) and explain the reasoning in one sentence.
- Memory: when the farmer refers to an earlier problem ("still there", "same problem"), use the memory/history context and mention what they reported before. If the history shows a recurring problem, ask whether it has spread.
- Language: write every farmer-facing field in the selected language using its native script (Telugu script for Telugu, Devanagari for Hindi). Keep common agricultural terms farmers actually use (e.g. "యూరియా", "DAP", "neem"). Use simple words.
- Mode: quick for everyday questions (speech 30-60 seconds), explain when asked why/how or for more details (up to 2 minutes), emergency for floods, storms, severe sudden damage, pest outbreaks, extreme heat or anything threatening the whole crop (speech 10-20 seconds, immediate actions only).
- speech_text must be natural spoken language: short sentences, no lists, no symbols, no emojis, no markdown, never mention "AI", "Gemini" or internal processing.
"""

EMERGENCY_WORDS = [
    "flood", "flooded", "storm", "cyclone", "hail", "outbreak", "whole field", "entire crop", "dying", "destroyed", "heatwave",
    "వరద", "తుఫాను", "వడగళ్ళు", "పంట మొత్తం", "నాశనం", "చనిపోతున్నాయి", "పొలం మొత్తం",
    "बाढ़", "तूफान", "ओले", "पूरी फसल", "नष्ट", "मर रहे",
]


def looks_like_emergency(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in EMERGENCY_WORDS)


class GeminiUnavailable(RuntimeError):
    pass


async def _generate(contents: list, schema: type[T], system: str = SYSTEM_PROMPT, temperature: float = 0.4) -> T:
    if not _client:
        raise GeminiUnavailable("GEMINI_API_KEY is not configured")
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
    )
    global _last_good
    last_error: Exception | None = None
    # Two passes over the model list with a short back-off: Gemini 503s ("high demand") are usually brief.
    for attempt in range(2):
        if attempt:
            await asyncio.sleep(2)
        for model in _model_order(ignore_cooldown=attempt > 0):
            try:
                resp = await asyncio.wait_for(
                    _client.aio.models.generate_content(model=model, contents=contents, config=config), timeout=60
                )
                result = resp.parsed if isinstance(resp.parsed, schema) else schema.model_validate_json(resp.text)
                _last_good = model
                return result
            except errors.APIError as e:
                last_error = e
                if e.code in (404, 429, 500, 503, 504):
                    # rate-limited / missing models sit out a while; overloaded ones are retried next request
                    if e.code in (404, 429):
                        _cooldown_until[model] = time.monotonic() + (3600 if e.code == 404 else COOLDOWN_SECONDS)
                    log.warning("Gemini %s unavailable (%s), trying next model", model, e.code)
                    continue
                raise
            except Exception as e:  # timeout, malformed JSON etc. - try the next model
                last_error = e
                log.warning("Gemini %s failed: %r", model, e)
    raise GeminiUnavailable(f"All Gemini models failed: {last_error!r}")


COOLDOWN_SECONDS = 60
_last_good: str | None = None
_cooldown_until: dict[str, float] = {}


def _model_order(ignore_cooldown: bool = False) -> list[str]:
    """Last model that answered goes first; models in rate-limit cooldown are skipped."""
    models = [GEMINI_MODEL, *[m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]]
    if _last_good in models:
        models.remove(_last_good)
        models.insert(0, _last_good)
    if ignore_cooldown:
        return models
    now = time.monotonic()
    ready = [m for m in models if _cooldown_until.get(m, 0) <= now]
    return ready or models


def lang_name(code: str) -> str:
    return LANGUAGES.get(code, {}).get("name", "English")


async def advise(question: str, language: str, context: str, image_part: types.Part | None = None,
                 more_details: bool = False) -> AdvisorAnswer:
    hints = []
    if looks_like_emergency(question):
        hints.append("The message contains emergency keywords - check carefully whether this is a farm emergency.")
    if more_details:
        hints.append("The farmer pressed 'More details': use explain mode and give a fuller, still simple explanation.")
    if image_part is not None:
        hints.append(
            "A crop photo is attached. In 'noticed' describe only visible symptoms. In 'reason' list possible causes "
            "with severity (low/medium/high) using phrases like 'Based on the image' and 'Possible issue'. "
            "Mention what extra information (other side of leaf, whole plant photo, spread in field) would help. "
            "In 'warning' say to confirm with a local agricultural expert before applying chemicals."
        )
    prompt = (
        f"FARM CONTEXT\n{context}\n\n"
        f"Selected language: {lang_name(language)} ({language}). Answer in {lang_name(language)}.\n"
        + ("\n".join(hints) + "\n" if hints else "")
        + f"\nFARMER'S MESSAGE:\n{question or '(no text - see the photo)'}"
    )
    contents: list = [image_part, prompt] if image_part is not None else [prompt]
    return await _generate(contents, AdvisorAnswer)


async def transcribe(audio: bytes, mime_type: str, language_hint: str) -> Transcription:
    return await _generate(
        [
            types.Part.from_bytes(data=audio, mime_type=mime_type),
            f"Transcribe this farmer's spoken question exactly, in its original language and script. "
            f"Expected language: {lang_name(language_hint)}. Return the transcript and its BCP-47 language code.",
        ],
        Transcription,
        system="You are an accurate speech transcriber for Indian languages.",
        temperature=0,
    )


async def extract_diary(text: str, language: str, crop: str) -> DiaryExtraction:
    return await _generate(
        [
            f"Farmer's crop: {crop or 'unknown'}. Language: {lang_name(language)}.\n"
            f"Convert this spoken farm diary note into structured data. Severity is about crop problems "
            f"(none if everything is fine).\nNote: {text}"
        ],
        DiaryExtraction,
        system="You turn farmers' daily voice notes into structured farm records. Do not invent details.",
        temperature=0.2,
    )


async def diary_trend(entries: list[str], language: str, crop: str) -> TrendSummary:
    return await _generate(
        [
            f"Crop: {crop}. Diary entries, oldest first:\n" + "\n".join(entries)
            + f"\n\nDescribe the trend for the farmer in {lang_name(language)} and suggest the next step. "
            "Be cautious; recommend an expert visit if things are worsening."
        ],
        TrendSummary,
        system=SYSTEM_PROMPT,
        temperature=0.3,
    )


async def generate_alerts(context: str, language: str) -> GeneratedAlerts:
    return await _generate(
        [
            f"{context}\n\nCreate 1 to 4 personalised farm alerts for today in {lang_name(language)} using ONLY "
            "the weather, crop stage and diary information above. Priorities: urgent = act today to prevent "
            "serious loss (heavy rain, storm, outbreak); warning = needs attention soon; normal = routine. "
            "Examples: heavy rain -> check drainage; flowering stage -> monitor regularly; hot dry -> check moisture."
        ],
        GeneratedAlerts,
        system=SYSTEM_PROMPT,
        temperature=0.3,
    )


_GLOSSARY = {
    "te-IN": "mites=నల్లి, thrips=తామర పురుగులు, whitefly=తెల్లదోమ, aphids=పేనుబంక, jassids=పచ్చదోమ, "
             "stem borer=కాండం తొలుచు పురుగు, leaf curl=ఆకు ముడత, blight=ఆకుమచ్చ తెగులు, bollworm=కాయతొలుచు పురుగు, "
             "fall armyworm=కత్తెర పురుగు, damping-off=నారుకుళ్ళు, soil moisture=నేల తేమ, nursery=నారుమడి",
    "hi-IN": "mites=माइट (मकड़ी), thrips=थ्रिप्स, whitefly=सफेद मक्खी, aphids=माहू, jassids=हरा तेला, "
             "stem borer=तना छेदक, leaf curl=पत्ती मरोड़, blight=झुलसा, bollworm=सुंडी, fall armyworm=फॉल आर्मीवर्म, "
             "damping-off=आर्द्र गलन, soil moisture=मिट्टी की नमी, nursery=नर्सरी",
}


async def translate_lines(lines: list[str], language: str) -> list[str]:
    """Translate short farm task titles; returns the input unchanged for English or on failure."""
    if language == "en-IN" or not lines:
        return lines
    try:
        out = await _generate(
            [f"Translate each line into simple {lang_name(language)} that a farmer understands, in native script. "
             "Keep it short. Use the farmer terms from this glossary exactly; keep any other pest/disease "
             "name as the common local word or transliterate it - never translate it literally.\n"
             f"Glossary: {_GLOSSARY.get(language, '')}\n"
             "Return the same number of items in the same order.\n" + "\n".join(lines)],
            Translations,
            system="You translate agricultural task titles for Indian farmers.",
            temperature=0,
        )
        return out.items if len(out.items) == len(lines) else lines
    except GeminiUnavailable:
        return lines
