from typing import Optional

from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    """US-12 — Resultado de transcribir un audio con Whisper."""

    text: str
    language: str
    confidence: Optional[float] = None
