"""Crop image handling: validate, store, and package photos for Gemini vision."""
from google.genai import types
from sqlalchemy.orm import Session

from app.models.models import Upload

ALLOWED = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/heic": ".heic", "image/heif": ".heif"}
MAX_BYTES = 10 * 1024 * 1024


class InvalidImage(ValueError):
    pass


def validate(data: bytes, mime_type: str) -> None:
    if mime_type not in ALLOWED:
        raise InvalidImage(f"Unsupported image type {mime_type}. Use JPG, PNG or WEBP.")
    if len(data) > MAX_BYTES:
        raise InvalidImage("Image is larger than 10 MB.")
    if len(data) < 1000:
        raise InvalidImage("Image looks empty.")


def store(db: Session, farmer_id: int, data: bytes, mime_type: str) -> str:
    """Save the photo in the database and return its public path (served by routes/uploads.py)."""
    up = Upload(farmer_id=farmer_id, mime_type=mime_type, data=data)
    db.add(up)
    db.flush()  # assigns the id
    return f"/api/uploads/{up.id}"


def to_part(data: bytes, mime_type: str) -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime_type)
