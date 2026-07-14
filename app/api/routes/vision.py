"""US-Vision — Endpoint POST /api/v1/surveys/generate-from-image.

Recibe una imagen (upload) y un idioma opcional, y devuelve un borrador
de encuesta generado por Gemini Vision. **No persiste nada en Supabase**:
el frontend inyecta el JSON en el formulario de creación y el usuario decide
si crear la encuesta o guardarla como borrador.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from api.deps import get_current_user_id
from schemas.vision import VisionResponse
from services import vision_service

router = APIRouter(prefix="/surveys", tags=["AI Generation"])

_MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post(
    "/generate-from-image",
    response_model=VisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Generar un borrador de encuesta desde una imagen con IA (Gemini Vision)",
)
def generate_from_image(
    image: UploadFile = File(..., description="Imagen para analizar (JPEG, PNG, WebP, GIF)"),
    language: str = Form(default="es", description="Idioma de salida (ej. es, en)"),
    context: str = Form(default="", description="Contexto opcional para orientar la encuesta"),
    num_questions: int = Form(default=5, description="Número de preguntas a generar (1-12)"),
    _user_id: str = Depends(get_current_user_id),
):
    """Genera un borrador de encuesta a partir del análisis de una imagen.

    El frontend puede hidratar el formulario de creación con un único `setState(...)`.
    """
    if image.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Tipo de imagen no soportado: '{image.content_type}'. "
            f"Usa uno de: {', '.join(_ALLOWED_TYPES)}.",
        )

    image_bytes = image.file.read()

    if len(image_bytes) > _MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"La imagen excede el tamaño máximo de {_MAX_IMAGE_SIZE // (1024 * 1024)} MB.",
        )

    if len(image_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La imagen está vacía.",
        )

    try:
        return vision_service.generate_survey_from_image(
            image_bytes=image_bytes,
            language=language.strip().lower(),
            context=context.strip(),
            num_questions=num_questions,
        )
    except vision_service.GeminiConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except vision_service.GeminiParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
    except vision_service.GeminiProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
