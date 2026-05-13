from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from httpx import ConnectError

from schemas.survey import SurveyCreate, SurveyResponse
from schemas.results import SurveyResults
from services import supabase_service
from api.deps import get_current_user_id

router = APIRouter(prefix="/surveys", tags=["Surveys"])


def _get_owned_survey_or_error(survey_id: int, creator_id: str) -> dict:
    """Carga la encuesta y valida que pertenezca al usuario indicado."""
    survey = supabase_service.get_survey(survey_id)
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encuesta no encontrada.",
        )
    if survey.get("creator_id") != creator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permiso para operar sobre esta encuesta.",
        )
    return survey



# Endpoint para crear una encuesta con sus preguntas (publicar)
@router.post(
    "/",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una nueva encuesta",
)
def create_survey(
    payload: SurveyCreate,
    creator_id: str = Depends(get_current_user_id),
):
    """
    Recibe una encuesta con sus preguntas, la valida y la guarda en Supabase.
    """
    try:
        survey = supabase_service.create_survey(payload, creator_id)
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
def list_my_surveys(creator_id: str = Depends(get_current_user_id)):
    """Devuelve las encuestas del creador autenticado con su estado actual."""
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
    creator_id: str = Depends(get_current_user_id),
):
    """
    Cambia el estado de la encuesta a `active` ("Publicada").

    Una vez publicada, sus preguntas quedan bloqueadas para edición
    (ver guard de inmutabilidad en `api/deps.py`).
    """
    survey = _get_owned_survey_or_error(survey_id, creator_id)

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


# US-09 — Cierre de una encuesta (active -> closed, irreversible)
@router.patch(
    "/{survey_id}/close",
    response_model=SurveyResponse,
    summary="Cerrar una encuesta (acción irreversible)",
)
def close_survey(
    survey_id: int,
    creator_id: str = Depends(get_current_user_id),
):
    """
    Cambia el estado de la encuesta a `closed`. A partir de ese momento la
    encuesta deja de aceptar respuestas. Solo el creador puede cerrarla.
    """
    survey = _get_owned_survey_or_error(survey_id, creator_id)

    if survey.get("status") == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La encuesta ya está cerrada.",
        )
    if survey.get("status") != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo las encuestas activas pueden cerrarse.",
        )

    try:
        return supabase_service.close_survey(survey_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# US-10 — Resultados agregados de una encuesta (solo el creador)
@router.get(
    "/{survey_id}/results",
    response_model=SurveyResults,
    summary="Resultados agregados de una encuesta",
)
def get_survey_results(
    survey_id: int,
    creator_id: str = Depends(get_current_user_id),
):
    """
    Devuelve las métricas agregadas de la encuesta:
    - porcentajes por opción para preguntas `multiple_choice` y `yes_no`,
    - lista de textos para preguntas `open`.
    Solo el creador autenticado puede consultarlos.
    """
    survey = _get_owned_survey_or_error(survey_id, creator_id)

    try:
        return supabase_service.get_survey_results(survey)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
