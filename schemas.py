"""Pydantic schemas: API request/response bodies and Gemini structured-output contracts."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------- Gemini structured outputs ----------
class AdvisorAnswer(BaseModel):
    """What Gemini must return for every farmer question."""
    mode: str = Field(description="quick | explain | emergency. quick = short everyday answer; explain = farmer asked why/how or wants detail; emergency = severe damage, flood, storm, outbreak, extreme heat, sudden spread.")
    is_emergency: bool
    needs_followup: bool = Field(description="True if information is insufficient and you must ask ONE clarifying question instead of guessing.")
    followup_question: str = Field(description="The single short clarifying question, in the farmer's language. Empty if not needed.")
    noticed: str = Field(description="What I noticed - simple explanation, farmer's language. Empty if followup.")
    reason: str = Field(description="Possible reason / likely cause, hedged ('may be', 'likely'). Farmer's language.")
    actions: list[str] = Field(description="What you can do now - 2 to 5 short practical steps, farmer's language.")
    warning: str = Field(description="Important warning - safety, chemicals, when to call an expert. Farmer's language.")
    monitor: str = Field(description="What to monitor over the next few days. Farmer's language.")
    emergency_actions: list[str] = Field(description="Emergency only: immediate safe actions. Else empty.")
    emergency_do_not: list[str] = Field(description="Emergency only: what NOT to do. Else empty.")
    emergency_collect: list[str] = Field(description="Emergency only: information/photos to collect. Else empty.")
    emergency_contact: str = Field(description="Emergency only: when/whom to contact (agriculture officer, Rythu Bharosa Kendra, KVK, Kisan Call Centre 1800-180-1551). Else empty.")
    speech_text: str = Field(description="Speech-ready version for text-to-speech in the farmer's language: natural conversational short sentences, no markdown, no lists, no emojis, no symbols. Quick: 30-60 seconds of speech. Emergency: 10-20 seconds. Explain: up to 2 minutes.")
    summary_en: str = Field(description="One-line English summary of the question and advice, for the assistant's memory.")
    new_memory_facts: list[str] = Field(description="New durable facts about this farm learned from this message, in English (e.g. 'Chilli plants had white insects on leaves on 2026-10-04'). Empty if none.")
    more_details_available: bool = Field(description="True if a longer explanation would be useful.")


class DiaryExtraction(BaseModel):
    crop: str
    observation_en: str = Field(description="Concise English observation")
    severity: str = Field(description="none | low | medium | high")
    tags: list[str] = Field(description="short english tags e.g. pest, disease, growth, irrigation, weather")
    acknowledgement: str = Field(description="One or two short sentences in the farmer's language confirming what was recorded, speech-ready.")


class GeneratedAlert(BaseModel):
    kind: str = Field(description="weather | crop | irrigation | pest")
    priority: str = Field(description="normal | warning | urgent")
    text: str = Field(description="1-2 short spoken sentences in the farmer's language, specific and actionable")


class GeneratedAlerts(BaseModel):
    alerts: list[GeneratedAlert]


class TrendSummary(BaseModel):
    trend: str = Field(description="improving | stable | worsening | unclear")
    summary: str = Field(description="2-4 short sentences in the farmer's language describing the trend and what to do; speech-ready")


class Translations(BaseModel):
    items: list[str] = Field(description="Translations in the same order as the input lines")


class Transcription(BaseModel):
    text: str
    language: str = Field(description="BCP-47 code: te-IN, hi-IN, en-IN or other")


# ---------- API bodies ----------
class FarmerProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str = ""
    language: str = "te-IN"
    state: str = ""
    district: str = ""
    village: str = ""
    crop: str = ""
    crop_variety: str = ""
    land_acres: float | None = None
    soil_type: str = ""
    irrigation: str = ""
    sowing_date: date | None = None
    farming_stage: str = ""
    latitude: float | None = None
    longitude: float | None = None
    voice_gender: str = "female"
    voice_speed: float = 1.0


class ChatRequest(BaseModel):
    message: str = ""
    language: str | None = None
    more_details_for: int | None = Field(None, description="conversation id to expand with a detailed explanation")


class ChatResponse(BaseModel):
    id: int
    question: str
    language: str
    answer: AdvisorAnswer
    image_url: str | None = None
    created_at: datetime


class VoiceRequest(BaseModel):
    text: str
    language: str = "te-IN"
    voice: str | None = Field(None, description="'male', 'female' or an explicit Murf voiceId")
    speed: float = 1.0
    pitch: int = 0
    purpose: str = Field("normal", description="normal | emergency | reminder | educational")


class VoiceResponse(BaseModel):
    audio_url: str
    voice_id: str
    style: str | None = None
    cached: bool = False


class ReminderIn(BaseModel):
    title: str
    category: str = "monitoring"
    due_date: date


class ReminderOut(ReminderIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    done: bool


class AlertIn(BaseModel):
    text: str | None = None
    priority: str = "normal"
    kind: str = "crop"
    language: str | None = None
    auto: bool = Field(False, description="True = let Gemini generate personalised alerts from weather + crop stage")


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    text: str
    priority: str
    language: str
    audio_url: str | None
    read: bool
    created_at: datetime


class DiaryIn(BaseModel):
    text: str
    language: str | None = None


class DiaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    entry_date: date
    raw_text: str
    crop: str
    observation: str
    severity: str
    tags: list
