"""US-12 — Servicio de transcripción de audio con Whisper (OpenAI)."""

import io
from typing import Tuple

from core.config import settings

ALLOWED_CONTENT_TYPES = {
    "audio/webm",
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/ogg",
}

ALLOWED_EXTENSIONS = {"webm", "wav", "mp3", "mpeg", "mpga", "m4a", "ogg", "mp4"}

MAX_BYTES = 10 * 1024 * 1024  # 10 MB


class TranscriptionFormatError(ValueError):
    """Formato de audio no permitido (400)."""


class TranscriptionSizeError(ValueError):
    """Audio mayor al limite permitido (413)."""


class TranscriptionProviderError(RuntimeError):
    """Fallo del proveedor externo (502)."""


def _extension(filename: str) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def validate_audio(filename: str, content_type: str, data: bytes) -> None:
    """Valida formato (MIME/extension) y tamaño del audio."""
    if len(data) == 0:
        raise TranscriptionFormatError("El archivo de audio está vacío.")

    if len(data) > MAX_BYTES:
        raise TranscriptionSizeError(
            f"El audio excede el limite de {MAX_BYTES // (1024 * 1024)} MB."
        )

    ext = _extension(filename)
    mime = (content_type or "").lower()

    if ext not in ALLOWED_EXTENSIONS and mime not in ALLOWED_CONTENT_TYPES:
        raise TranscriptionFormatError(
            "Formato de audio no soportado. Use webm, mp3 o wav."
        )


def _build_client():
    if not settings.OPENAI_API_KEY:
        raise TranscriptionProviderError(
            "OPENAI_API_KEY no está configurada en el servidor."
        )
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise TranscriptionProviderError(
            "La libreria 'openai' no esta instalada en el servidor."
        ) from exc
    return OpenAI(api_key=settings.OPENAI_API_KEY)


def transcribe_audio(
    filename: str,
    content_type: str,
    data: bytes,
    language: str | None = None,
) -> Tuple[str, str, float | None]:
    """
    Llama a la API de Whisper y devuelve `(text, language, confidence)`.

    `confidence` es opcional: Whisper no expone una probabilidad por respuesta,
    pero si el modelo entrega `avg_logprob` lo convertimos en un score [0, 1]
    para que el frontend pueda aplicar el umbral de US-15.
    """
    validate_audio(filename, content_type, data)

    client = _build_client()
    lang = language or settings.WHISPER_DEFAULT_LANGUAGE

    buffer = io.BytesIO(data)
    buffer.name = filename or f"audio.{(_extension(filename) or 'webm')}"

    try:
        result = client.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=buffer,
            language=lang,
            response_format="verbose_json",
        )
    except Exception as exc:
        raise TranscriptionProviderError(
            f"Fallo del proveedor de transcripcion: {exc}"
        ) from exc

    text = getattr(result, "text", "") or ""
    detected_language = getattr(result, "language", None) or lang
    confidence = _score_from_segments(getattr(result, "segments", None))

    return text.strip(), detected_language, confidence


def _score_from_segments(segments) -> float | None:
    """Convierte el `avg_logprob` promedio en un score [0, 1] (mayor = mejor)."""
    if not segments:
        return None

    log_probs: list[float] = []
    for segment in segments:
        if isinstance(segment, dict):
            value = segment.get("avg_logprob")
        else:
            value = getattr(segment, "avg_logprob", None)
        if value is not None:
            log_probs.append(float(value))

    if not log_probs:
        return None

    import math

    avg = sum(log_probs) / len(log_probs)
    return round(math.exp(avg), 4)
