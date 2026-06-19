import csv
import io

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse
from typing import List, Optional
from httpx import ConnectError

from schemas.survey import SurveyCreate, SurveyResponse
from schemas.draft import DraftPayload
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


# Endpoint para crear una encuesta con sus preguntas (validacion estricta)
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
    """Recibe una encuesta con sus preguntas, la valida y la guarda en Supabase."""
    try:
        survey = supabase_service.create_survey(payload, creator_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    return survey


# Crear borrador con contenido parcial.
# Importante: la ruta estatica `/draft` se declara ANTES de `/{survey_id}` para
# que FastAPI no la confunda con un id dinamico.
@router.post(
    "/draft",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un borrador (permite contenido parcial)",
)
def create_draft(
    payload: DraftPayload,
    creator_id: str = Depends(get_current_user_id),
):
    try:
        return supabase_service.create_draft(payload, creator_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


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


# US-04 — Publicacion de una encuesta (draft -> active)
@router.patch(
    "/{survey_id}/publish",
    response_model=SurveyResponse,
    summary="Publicar una encuesta",
)
def publish_survey(
    survey_id: int,
    creator_id: str = Depends(get_current_user_id),
):
    """Cambia el estado de la encuesta a `active` (Publicada)."""
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
    summary="Cerrar una encuesta (accion irreversible)",
)
def close_survey(
    survey_id: int,
    creator_id: str = Depends(get_current_user_id),
):
    """Cambia el estado de la encuesta a `closed`. Solo el creador puede cerrarla."""
    survey = _get_owned_survey_or_error(survey_id, creator_id)

    if survey.get("status") == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La encuesta ya esta cerrada.",
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
    """Devuelve las metricas agregadas de la encuesta."""
    survey = _get_owned_survey_or_error(survey_id, creator_id)

    try:
        return supabase_service.get_survey_results(survey)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# Obtener una encuesta por id (incluye sus preguntas) — para reabrir un borrador.
@router.get(
    "/{survey_id}",
    response_model=SurveyResponse,
    summary="Obtener una encuesta por id (incluye preguntas)",
)
def get_survey_by_id(
    survey_id: int,
    creator_id: str = Depends(get_current_user_id),
):
    _get_owned_survey_or_error(survey_id, creator_id)
    survey = supabase_service.get_survey_with_questions(survey_id)
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Encuesta no encontrada.",
        )
    return survey


# Actualizar un borrador existente (reemplaza preguntas).
@router.put(
    "/{survey_id}/draft",
    response_model=SurveyResponse,
    summary="Actualizar un borrador existente",
)
def update_draft(
    survey_id: int,
    payload: DraftPayload,
    creator_id: str = Depends(get_current_user_id),
):
    survey = _get_owned_survey_or_error(survey_id, creator_id)
    if survey.get("status") != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Solo se pueden editar encuestas en estado borrador.",
        )
    try:
        return supabase_service.update_draft(survey_id, payload)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


# Exportar resultados a CSV
@router.get(
    "/{survey_id}/results/csv",
    summary="Exportar resultados de una encuesta a CSV",
)
def export_survey_results_csv(
    survey_id: int,
    creator_id: str = Depends(get_current_user_id),
):
    """
    Descarga un archivo CSV con todas las respuestas de la encuesta.
    Cada fila representa una respuesta individual a una pregunta.
    Ordenado por ID de respuesta y posición de la pregunta.
    Solo el creador autenticado puede exportar.
    """
    _get_owned_survey_or_error(survey_id, creator_id)

    try:
        rows = supabase_service.get_survey_responses_raw(survey_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID Respuesta",
        "Fecha de envío",
        "NumPregunta",
        "Pregunta",
        "Tipo",
        "Respuesta",
    ])
    for row in rows:
        writer.writerow([
            row["response_id"],
            row["submitted_at"],
            row["question_position"],
            row["question_content"],
            row["question_type"],
            row["answer_text"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="encuesta_{survey_id}_resultados.csv"'
            ),
        },
    )
