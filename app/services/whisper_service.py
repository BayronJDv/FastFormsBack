"""US-12 — Servicio de transcripción de audio con Whisper.

Soporta dos proveedores, seleccionables con `WHISPER_PROVIDER`:

- ``local``  → paquete open-source ``openai-whisper`` (https://github.com/openai/whisper).
  Corre el modelo en la propia máquina; no necesita API key, cuota ni billing.
  Requiere `ffmpeg` instalado en el sistema.
- ``openai`` → API hospedada de OpenAI (modelo ``whisper-1``). Necesita
  `OPENAI_API_KEY` con saldo disponible.

Por defecto se usa ``local`` para no depender de la cuota de OpenAI.
"""

import io
import math
import os
import subprocess
import tempfile

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

# Cache del modelo local: cargarlo es costoso, así que se hace una sola vez.
_local_model = None

# Frecuencia de muestreo que espera openai-whisper (16 kHz mono).
_WHISPER_SAMPLE_RATE = 16000


def _ffmpeg_exe() -> str:
    """Devuelve la ruta al binario de ffmpeg a usar.

    Prioriza el binario empaquetado por `imageio-ffmpeg` (su nombre real es
    versionado, p. ej. `ffmpeg-win64-v4.2.2.exe`, por eso lo invocamos por
    ruta absoluta en vez de depender del PATH). Si no está disponible, cae al
    `ffmpeg` del sistema.
    """
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _load_audio(path: str, sample_rate: int = _WHISPER_SAMPLE_RATE):
    """Decodifica un archivo de audio a un arreglo float32 mono normalizado.

    Replica `whisper.load_audio` pero invocando ffmpeg por ruta absoluta, de
    modo que funcione aunque el binario no se llame literalmente `ffmpeg` ni
    esté en el PATH (caso típico en Windows con `imageio-ffmpeg`).
    """
    cmd = [
        _ffmpeg_exe(),
        "-nostdin",
        "-threads", "0",
        "-i", path,
        "-f", "s16le",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise TranscriptionProviderError(
            "No se encontro 'ffmpeg'. Instala 'imageio-ffmpeg' "
            "('pip install imageio-ffmpeg') para usar el binario empaquetado, "
            "o instala ffmpeg en el sistema y asegurate de que este en el PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise TranscriptionProviderError(
            f"ffmpeg no pudo decodificar el audio: {detail[-300:]}"
        ) from exc

    import numpy as np

    return np.frombuffer(proc.stdout, np.int16).astype(np.float32) / 32768.0


class TranscriptionFormatError(ValueError):
    """Formato de audio no permitido (400)."""


class TranscriptionSizeError(ValueError):
    """Audio mayor al limite permitido (413)."""


class TranscriptionProviderError(RuntimeError):
    """Fallo del proveedor de transcripción (502)."""


class ModelNotLoadedError(RuntimeError):
    """El modelo local de Whisper no se pudo cargar (503)."""


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


def _resolve_language(language: str | None) -> str | None:
    """Traduce el parámetro de idioma del cliente al que espera Whisper.

    - ``None`` / ``""``  → idioma por defecto (``WHISPER_DEFAULT_LANGUAGE``).
    - ``"auto"``         → ``None`` (Whisper detecta el idioma solo, US-18).
    - código específico  → se respeta tal cual.
    """
    if language is None or language == "":
        return settings.WHISPER_DEFAULT_LANGUAGE
    if language.strip().lower() == "auto":
        return None
    return language


def transcribe_audio(
    filename: str,
    content_type: str,
    data: bytes,
    language: str | None = None,
    task: str = "transcribe",
) -> dict:
    """
    Transcribe el audio y devuelve un dict
    ``{text, language, confidence, segments}``.

    - ``language``: código ISO (``"es"``), ``"auto"`` para detección automática
      (US-18), o ``None`` para usar el idioma por defecto.
    - ``task``: ``"transcribe"`` (mismo idioma) o ``"translate"`` (traduce a
      inglés usando el modo de traducción de Whisper, US-18).
    - ``confidence`` proviene del ``avg_logprob`` por segmento, mapeado a
      ``[0, 1]`` para el umbral de US-15.

    Despacha al proveedor configurado en ``WHISPER_PROVIDER``.
    """
    validate_audio(filename, content_type, data)

    lang = _resolve_language(language)
    task = task if task in ("transcribe", "translate") else "transcribe"
    provider = (settings.WHISPER_PROVIDER or "local").lower()

    if provider == "openai":
        return _transcribe_openai(filename, data, lang, task)
    return _transcribe_local(filename, data, lang, task)


# ---------------------------------------------------------------------------
# Proveedor local — openai/whisper (sin API key)
# ---------------------------------------------------------------------------

def _get_local_model():
    """Carga (una sola vez) el modelo local de openai-whisper."""
    global _local_model
    if _local_model is not None:
        return _local_model

    try:
        import whisper  # paquete: openai-whisper
    except ImportError as exc:
        raise ModelNotLoadedError(
            "La libreria 'openai-whisper' no esta instalada en el servidor. "
            "Instalala con 'pip install openai-whisper'."
        ) from exc

    try:
        _local_model = whisper.load_model(settings.WHISPER_LOCAL_MODEL)
    except Exception as exc:
        raise ModelNotLoadedError(
            f"No se pudo cargar el modelo Whisper local "
            f"'{settings.WHISPER_LOCAL_MODEL}': {exc}"
        ) from exc

    return _local_model


def warm_up() -> bool:
    """US-12 — Pre-carga el modelo local (llamado en el startup del backend).

    Devuelve True si quedó cargado, False si falló (sin lanzar, para no
    abortar el arranque; el primer /transcribe reportará el 503 si procede).
    """
    if (settings.WHISPER_PROVIDER or "local").lower() != "local":
        return False
    try:
        _get_local_model()
        return True
    except Exception:
        return False


def _transcribe_local(
    filename: str, data: bytes, language: str | None, task: str = "transcribe"
) -> dict:
    model = _get_local_model()

    # Volcamos los bytes a un temporal y decodificamos el audio nosotros mismos
    # (con la ruta absoluta del ffmpeg empaquetado) para entregarle a Whisper un
    # arreglo numpy. Así evitamos que openai-whisper invoque `ffmpeg` por nombre,
    # que falla en Windows cuando el binario no se llama literalmente `ffmpeg`.
    ext = _extension(filename) or "webm"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        audio = _load_audio(tmp_path)
        result = model.transcribe(
            audio, language=language, task=task, fp16=False
        )
    except (TranscriptionProviderError, ModelNotLoadedError):
        raise
    except Exception as exc:
        raise TranscriptionProviderError(
            f"Fallo al transcribir localmente con Whisper: {exc}."
        ) from exc
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    text = (result.get("text") or "").strip()
    detected_language = result.get("language") or language or "es"
    segments = _extract_segments(result.get("segments"))
    confidence = _score_from_segments(result.get("segments"))

    return {
        "text": text,
        "language": detected_language,
        "confidence": confidence,
        "segments": segments,
    }


# ---------------------------------------------------------------------------
# Proveedor hospedado — API de OpenAI
# ---------------------------------------------------------------------------

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


def _transcribe_openai(
    filename: str, data: bytes, language: str | None, task: str = "transcribe"
) -> dict:
    client = _build_client()

    buffer = io.BytesIO(data)
    buffer.name = filename or f"audio.{(_extension(filename) or 'webm')}"

    # La API expone la traducción como un endpoint distinto.
    endpoint = (
        client.audio.translations if task == "translate"
        else client.audio.transcriptions
    )
    kwargs = {
        "model": settings.WHISPER_MODEL,
        "file": buffer,
        "response_format": "verbose_json",
    }
    if task != "translate" and language:
        kwargs["language"] = language

    try:
        result = endpoint.create(**kwargs)
    except Exception as exc:
        # Mensaje específico cuando la cuenta no tiene cuota/billing (429).
        if "insufficient_quota" in str(exc) or "429" in str(exc):
            raise TranscriptionProviderError(
                "La cuenta de OpenAI no tiene cuota disponible (429). Carga "
                "saldo en platform.openai.com o usa WHISPER_PROVIDER=local."
            ) from exc
        raise TranscriptionProviderError(
            f"Fallo del proveedor de transcripcion: {exc}"
        ) from exc

    text = getattr(result, "text", "") or ""
    detected_language = getattr(result, "language", None) or language or "es"
    raw_segments = getattr(result, "segments", None)
    return {
        "text": text.strip(),
        "language": detected_language,
        "confidence": _score_from_segments(raw_segments),
        "segments": _extract_segments(raw_segments),
    }


# ---------------------------------------------------------------------------
# Utilidades comunes
# ---------------------------------------------------------------------------

def _extract_segments(segments) -> list[dict]:
    """Normaliza los segmentos de Whisper a `[{start, end, text}]`."""
    if not segments:
        return []
    out: list[dict] = []
    for segment in segments:
        if isinstance(segment, dict):
            start = segment.get("start")
            end = segment.get("end")
            text = segment.get("text")
        else:
            start = getattr(segment, "start", None)
            end = getattr(segment, "end", None)
            text = getattr(segment, "text", None)
        if text is None:
            continue
        out.append(
            {
                "start": round(float(start or 0.0), 3),
                "end": round(float(end or 0.0), 3),
                "text": str(text).strip(),
            }
        )
    return out


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

    avg = sum(log_probs) / len(log_probs)
    return round(math.exp(avg), 4)
