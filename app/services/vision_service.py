"""US-Vision — Servicio de generación de encuestas desde imágenes con Gemini Vision.

Composición:
  - Carga el prompt maestro desde `prompts/promptVisionV1.txt`.
  - Recibe bytes de imagen y los codifica en base64 para enviar a Gemini.
  - Delega en Gemini (`gemini_service._build_client`) con `response_schema`
    estructurado para garantizar JSON válido.

Excepciones tipadas (re-exportadas desde `gemini_service`):
  * ``GeminiConfigError``     → 503 (API key no configurada / SDK no instalada).
  * ``GeminiProviderError``   → 502 (fallo del proveedor Gemini).
  * ``GeminiParseError``      → 502 (la respuesta no parsea o no cumple el schema).

La salida final es un dict compatible con ``VisionResponse``.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from services import gemini_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Re-exports — el router mapea estas excepciones a HTTP sin importar
# `gemini_service` directamente.
# ---------------------------------------------------------------------------

GeminiConfigError = gemini_service.GeminiConfigError
GeminiProviderError = gemini_service.GeminiProviderError
GeminiParseError = gemini_service.GeminiParseError


# ---------------------------------------------------------------------------
# Prompt maestro
# ---------------------------------------------------------------------------

_PROMPT_FILE = Path(__file__).resolve().parents[2] / "prompts/promptVisionV1.txt"

_prompt_cache: Optional[str] = None
_prompt_mtime: Optional[float] = None


def _load_master_prompt() -> str:
    """Lee ``prompts/promptVisionV1.txt`` con caché por mtime."""
    global _prompt_cache, _prompt_mtime

    if not _PROMPT_FILE.exists():
        raise GeminiConfigError(
            f"No se encontró el archivo de prompt maestro en '{_PROMPT_FILE}'."
        )

    mtime = _PROMPT_FILE.stat().st_mtime
    if _prompt_cache is None or mtime != _prompt_mtime:
        _prompt_cache = _PROMPT_FILE.read_text(encoding="utf-8")
        _prompt_mtime = mtime
    return _prompt_cache


def _render_prompt(master: str, language: str, context: str = "", num_questions: int = 5) -> str:
    """Sustituye los placeholders del prompt maestro."""
    ctx = context if context else "No se proporcionó contexto adicional."
    return (
        master.replace("{language}", language)
              .replace("{context}", ctx)
              .replace("{num_questions}", str(num_questions))
    )


# ---------------------------------------------------------------------------
# Esquema de respuesta para Gemini (response_schema)
# ---------------------------------------------------------------------------

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Título corto de la encuesta."},
        "description": {"type": "string", "description": "Descripción breve de la encuesta."},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "question_type": {
                        "type": "string",
                        "enum": ["open", "multiple_choice", "yes_no"],
                    },
                    "options": {
                        "anyOf": [
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                    "position": {"type": "integer"},
                },
                "required": ["content", "question_type", "options", "position"],
            },
        },
    },
    "required": ["title", "description", "questions"],
}


# ---------------------------------------------------------------------------
# Validación con Pydantic (capa de seguridad adicional al response_schema)
# ---------------------------------------------------------------------------


class _VisionGeminiQuestion(BaseModel):
    content: Any
    question_type: Any
    options: Any
    position: Any


class _GeminiVisionResponse(BaseModel):
    title: Any
    description: Any = ""
    questions: list[_VisionGeminiQuestion] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Saneamiento: defensa en profundidad sobre la salida de Gemini
# ---------------------------------------------------------------------------

_ALLOWED_TYPES = {"open", "multiple_choice", "yes_no"}


def _sanitize_question_type(raw) -> str:
    """Normaliza el tipo de pregunta; default a 'open' si no es válido."""
    if raw is None or raw == "":
        return "open"
    try:
        candidate = str(raw).strip().lower()
    except Exception:
        return "open"
    if candidate in _ALLOWED_TYPES:
        return candidate
    aliases = {
        "choice": "multiple_choice",
        "multiple": "multiple_choice",
        "multi": "multiple_choice",
        "mc": "multiple_choice",
        "boolean": "yes_no",
        "si_no": "yes_no",
        "sí_no": "yes_no",
    }
    return aliases.get(candidate, "open")


def _sanitize_options(raw, question_type: str) -> Optional[list[str]]:
    """Limpia y valida las opciones según el tipo de pregunta."""
    if question_type == "multiple_choice":
        if not isinstance(raw, list):
            return None
        cleaned = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        return cleaned if len(cleaned) >= 2 else None
    return None


def _sanitize_position(raw, index: int) -> int:
    """Garantiza posición secuencial."""
    try:
        pos = int(raw)
        if pos >= 0:
            return pos
    except (TypeError, ValueError):
        pass
    return index


def _sanitize_title(raw) -> str:
    cleaned = (raw or "").strip()
    return cleaned if cleaned else "Encuesta basada en imagen"


def _sanitize_description(raw) -> str:
    cleaned = (raw or "").strip()
    return cleaned if cleaned else "Encuesta generada a partir del análisis de una imagen."


# ---------------------------------------------------------------------------
# Llamada a Gemini (re-usa el cliente de gemini_service)
# ---------------------------------------------------------------------------


def _call_gemini_for_vision(prompt: str, image_bytes: bytes) -> str:
    """Invoca a Gemini Vision con imagen inline + prompt y devuelve el texto crudo."""
    client = gemini_service._build_client()

    try:
        from google.genai import types
    except ImportError as exc:
        raise GeminiConfigError(
            "La librería 'google-genai' no está instalada en el servidor."
        ) from exc

    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    image_part = types.Part.from_bytes(
        data=base64.b64decode(image_b64),
        mime_type="image/jpeg",
    )

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=_RESPONSE_SCHEMA,
        temperature=0.7,
    )
    try:
        response = client.models.generate_content(
            model=gemini_service.settings.GEMINI_MODEL,
            contents=[prompt, image_part],
            config=config,
        )
    except Exception as exc:
        text = str(exc)
        if "429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
            raise GeminiProviderError(
                "La cuenta de Gemini no tiene cuota disponible (429)."
            ) from exc
        raise GeminiProviderError(f"Fallo del proveedor Gemini: {exc}") from exc

    raw = (getattr(response, "text", None) or "").strip()
    if not raw:
        raise GeminiProviderError("Gemini devolvió una respuesta vacía.")
    return raw


def _parse_and_validate(raw_text: str) -> dict:
    """Parsea y valida la respuesta cruda de Gemini Vision.

    Devuelve un dict con claves normalizadas.
    """
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GeminiParseError(
            f"La respuesta de Gemini no es JSON válido: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise GeminiParseError(
            "La respuesta de Gemini no es un objeto JSON de primer nivel."
        )

    title = _sanitize_title(data.get("title"))
    description = _sanitize_description(data.get("description"))

    raw_questions = data.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise GeminiParseError(
            "La respuesta de Gemini no contiene preguntas válidas."
        )

    questions = []
    for idx, rq in enumerate(raw_questions):
        if not isinstance(rq, dict):
            continue

        q_type = _sanitize_question_type(rq.get("question_type"))
        options = _sanitize_options(rq.get("options"), q_type)
        position = _sanitize_position(rq.get("position"), idx)
        content = (rq.get("content") or "").strip()

        if not content:
            continue

        question = {
            "content": content,
            "question_type": q_type,
            "options": options,
            "position": position,
        }
        questions.append(question)

    if not questions:
        raise GeminiParseError(
            "La respuesta de Gemini no generó preguntas válidas después del saneamiento."
        )

    return {
        "title": title,
        "description": description,
        "questions": questions,
    }


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def generate_survey_from_image(
    image_bytes: bytes,
    language: str = "es",
    context: str = "",
    num_questions: int = 5,
) -> dict:
    """Genera un borrador de encuesta a partir de una imagen.

    Devuelve un dict ``{title, description, questions: [{content, question_type, options, position}, ...]}``
    que el frontend puede inyectar directamente en el formulario de creación.

    Lanza:
      - ``GeminiConfigError``     si falta la API key o la SDK.
      - ``GeminiProviderError``   si Gemini falla (red, 429, 5xx).
      - ``GeminiParseError``      si la respuesta no parsea o no valida.
    """
    master = _load_master_prompt()
    final_prompt = _render_prompt(master, language, context, num_questions)

    logger.info(
        "Generando encuesta desde imagen con Gemini Vision: model=%s lang=%s num_q=%d img_size=%d",
        gemini_service.settings.GEMINI_MODEL,
        language,
        num_questions,
        len(image_bytes),
    )

    raw = _call_gemini_for_vision(final_prompt, image_bytes)
    return _parse_and_validate(raw)
