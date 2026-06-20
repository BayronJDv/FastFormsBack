"""US-12 / US-18 / US-19 — Endpoint POST /transcribe (Whisper local)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.deps import get_optional_user_id
from schemas.transcribe import TranscribeResponse
from services import voice_code, whisper_service

router = APIRouter(prefix="/transcribe", tags=["Voice"])


def _run_transcription(
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str | None,
    task: str,
    normalize: str | None,
) -> TranscribeResponse:
    try:
        result = whisper_service.transcribe_audio(
            filename=filename or "audio.webm",
            content_type=content_type or "",
            data=audio_bytes,
            language=language,
            task=task or "transcribe",
        )
    except whisper_service.TranscriptionFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except whisper_service.TranscriptionSizeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )
    except whisper_service.ModelNotLoadedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except whisper_service.TranscriptionProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    # US-19 — Normalización opcional a código de encuesta.
    normalized_code = None
    if normalize == "code":
        normalized_code = voice_code.normalize_spoken_code(result["text"])

    return TranscribeResponse(
        text=result["text"],
        language=result["language"],
        confidence=result.get("confidence"),
        segments=result.get("segments", []),
        normalized_code=normalized_code,
    )


@router.post(
    "/",
    response_model=TranscribeResponse,
    summary="Transcribe un audio corto con Whisper local",
)
async def transcribe(
    audio: UploadFile = File(..., description="Audio webm/mp3/wav, ≤ 60s, ≤ 10MB"),
    language: str | None = Form(
        default=None, description='Código ISO, "auto" para detectar (US-18)'
    ),
    task: str = Form(
        default="transcribe", description='"transcribe" o "translate" (US-18)'
    ),
    normalize: str | None = Form(
        default=None, description='"code" para normalizar a código (US-19)'
    ),
    _user_id: str | None = Depends(get_optional_user_id),
):
    data = await audio.read()
    return _run_transcription(
        audio_bytes=data,
        filename=audio.filename or "audio.webm",
        content_type=audio.content_type or "",
        language=language,
        task=task,
        normalize=normalize,
    )


@router.post(
    "",
    response_model=TranscribeResponse,
    include_in_schema=False,
)
async def transcribe_no_slash(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    task: str = Form(default="transcribe"),
    normalize: str | None = Form(default=None),
    user_id: str | None = Depends(get_optional_user_id),
):
    data = await audio.read()
    return _run_transcription(
        audio_bytes=data,
        filename=audio.filename or "audio.webm",
        content_type=audio.content_type or "",
        language=language,
        task=task,
        normalize=normalize,
    )
