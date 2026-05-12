from fastapi import APIRouter, HTTPException, Header, status
from typing import Optional
from httpx import ConnectError

from schemas.survey import SurveyCreate, SurveyResponse
from services import supabase_service

router = APIRouter(prefix="/surveys", tags=["Surveys"])

# UUID de prueba válido para usar hasta que Auth (US-01) esté implementado
_TEST_CREATOR_ID = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"


def _resolve_creator_id(x_creator_id: Optional[str]) -> str:
    # TODO: reemplazar con el ID real del usuario autenticado (US-01)
    return x_creator_id or _TEST_CREATOR_ID


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

    **Nota:** El `creator_id` se obtiene del header `x-creator-id`.
    Será reemplazado por el token de Supabase Auth en US-01.
    """
    creator_id = _resolve_creator_id(x_creator_id)

    try:
        survey = supabase_service.create_survey(payload, creator_id)
    except ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo conectar con la base de datos. Verifica la configuración de SUPABASE_URL.",
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return survey


# US-02 — Listado de encuestas del usuario autenticado
@router.get(
    "/",
    response_model=List[SurveyResponse],
    summary="Listar las encuestas del usuario autenticado",
)
def list_my_surveys(x_creator_id: Optional[str] = Header(default=None)):
    """Devuelve las encuestas del creador autenticado con su estado actual."""
    creator_id = _resolve_creator_id(x_creator_id)

    try:
        return supabase_service.list_surveys_by_creator(creator_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# US-04 — Publicación de una encuesta (draft -> active)
@router.patch(
    "/{survey_id}/publish",
    response_model=SurveyResponse,
    summary="Publicar una encuesta",
)
def publish_survey(
    survey_id: int,
    x_creator_id: Optional[str] = Header(default=None),
):
    """
    Cambia el estado de la encuesta a `active` ("Publicada").

    Una vez publicada, sus preguntas quedan bloqueadas para edición
    (ver guard de inmutabilidad en `api/deps.py`).
    """
    creator_id = _resolve_creator_id(x_creator_id)

    survey = supabase_service.get_survey(survey_id)
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encuesta no encontrada.",
        )
    if survey.get("creator_id") != creator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No puedes publicar una encuesta que no te pertenece.",
        )
    if survey.get("status") != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo las encuestas en borrador pueden publicarse.",
        )

    try:
        return supabase_service.set_survey_status(survey_id, "active")
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
