"""Database tables."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


def now():
    return datetime.now()


class Farmer(Base):
    __tablename__ = "farmers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    language: Mapped[str] = mapped_column(String(10), default="te-IN")
    state: Mapped[str] = mapped_column(String(100), default="")
    district: Mapped[str] = mapped_column(String(100), default="")
    village: Mapped[str] = mapped_column(String(100), default="")
    crop: Mapped[str] = mapped_column(String(100), default="")
    crop_variety: Mapped[str] = mapped_column(String(100), default="")
    land_acres: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_type: Mapped[str] = mapped_column(String(100), default="")
    irrigation: Mapped[str] = mapped_column(String(100), default="")
    sowing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    farming_stage: Mapped[str] = mapped_column(String(100), default="")  # manual override; else computed
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_gender: Mapped[str] = mapped_column(String(10), default="female")
    voice_speed: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Conversation(Base):
    """One farmer question + assistant answer."""
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10))
    image_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response: Mapped[dict] = mapped_column(JSON)  # structured advisor response
    speech_text: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")  # short English summary used as memory
    mode: Mapped[str] = mapped_column(String(20), default="quick")
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class MemoryFact(Base):
    """Durable facts the assistant learned about this farm (symptoms, treatments tried, ...)."""
    __tablename__ = "memory_facts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    fact: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Reminder(Base):
    __tablename__ = "reminders"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(30), default="monitoring")  # irrigation|monitoring|pest|water|harvest|other
    due_date: Mapped[date] = mapped_column(Date)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="crop")  # weather|crop|irrigation|pest|emergency
    text: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # normal|warning|urgent
    language: Mapped[str] = mapped_column(String(10))
    audio_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Upload(Base):
    """Crop photos live in the database so they survive restarts on hosts with ephemeral disks (Render)."""
    __tablename__ = "uploads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    mime_type: Mapped[str] = mapped_column(String(50))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date)
    raw_text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10))
    crop: Mapped[str] = mapped_column(String(100), default="")
    observation: Mapped[str] = mapped_column(Text, default="")  # English, structured
    severity: Mapped[str] = mapped_column(String(10), default="none")  # none|low|medium|high
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
