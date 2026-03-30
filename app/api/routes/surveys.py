from fastapi import APIRouter, HTTPException, Header, status
from typing import Optional

from schemas.survey import SurveyCreate, SurveyResponse
from services import supabase_service

router = APIRouter(prefix="/surveys", tags=["Surveys"])

# UUID de prueba válido para usar hasta que Auth (US-01) esté implementado
_TEST_CREATOR_ID = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"

# Endpoint para crear una encuesta con sus preguntas
@router.post(
    "/",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva encuesta",
)
def create_survey(
    payload: SurveyCreate,
    x_creator_id: Optional[str] = Header(default=None),
):
    """
    Recibe una encuesta con sus preguntas, la valida y la guarda en Supabase.

    **Validaciones aplicadas:**
    - El título no puede estar vacío.
    - Mínimo 1 pregunta, máximo 12.
    - Cada pregunta debe tener un enunciado (`content`).
    - Preguntas de tipo `multiple_choice` requieren al menos 2 opciones.
    - Preguntas de tipo `open` o `yes_no` no deben incluir opciones.
    - No puede haber dos preguntas con la misma posición.

    **Nota:** El `creator_id` se obtiene del header `x-creator-id`.
    Será reemplazado por el token de Supabase Auth en US-01.
    """

    # TODO: reemplazar con el ID real del usuario autenticado (US-01)
    creator_id = x_creator_id or _TEST_CREATOR_ID

    try:
        survey = supabase_service.create_survey(payload, creator_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return survey