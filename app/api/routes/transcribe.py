"""US-12 — Endpoint POST /transcribe (Whisper)."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.deps import get_optional_user_id
from schemas.transcribe import TranscribeResponse
from services import whisper_service

router = APIRouter(prefix="/transcribe", tags=["Voice"])


@router.post(
    "/",
    response_model=TranscribeResponse,
    summary="Transcribe un audio corto con Whisper",
)
async def transcribe(
    audio: UploadFile = File(..., description="Audio webm/mp3/wav, ≤ 60s, ≤ 10MB"),
    language: str | None = Form(default=None),
    _user_id: str | None = Depends(get_optional_user_id),
):
    data = await audio.read()
    try:
        text, detected_language, confidence = whisper_service.transcribe_audio(
            filename=audio.filename or "audio.webm",
            content_type=audio.content_type or "",
            data=data,
            language=language,
        )
    except whisper_service.TranscriptionFormatError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except whisper_service.TranscriptionSizeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        )
    except whisper_service.TranscriptionProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return TranscribeResponse(
        text=text, language=detected_language, confidence=confidence
    )


@router.post(
    "",
    response_model=TranscribeResponse,
    include_in_schema=False,
)
async def transcribe_no_slash(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    user_id: str | None = Depends(get_optional_user_id),
):
    return await transcribe(audio=audio, language=language, _user_id=user_id)
