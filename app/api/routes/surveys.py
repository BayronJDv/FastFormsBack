from fastapi import APIRouter, HTTPException, Header, status
from typing import Optional, List

from schemas.survey import SurveyCreate, SurveyResponse
from schemas.draft import DraftPayload
from services import supabase_service

router = APIRouter(prefix="/surveys", tags=["Surveys"])

# UUID de prueba valido para usar hasta que Auth (US-01) este implementado
_TEST_CREATOR_ID = "832071cb-5f6a-4d2d-8c0c-901cd13e78ad"


# Endpoint para crear una encuesta con sus preguntas (publicar)
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
    - El titulo no puede estar vacio.
    - Minimo 1 pregunta, maximo 12.
    - Cada pregunta debe tener un enunciado (`content`).
    - Preguntas de tipo `multiple_choice` requieren al menos 2 opciones.
    - Preguntas de tipo `open` o `yes_no` no deben incluir opciones.
    - No puede haber dos preguntas con la misma posicion.
    """

    creator_id = x_creator_id or _TEST_CREATOR_ID

    try:
        survey = supabase_service.create_survey(payload, creator_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    return survey


# ---------------------------------------------------------------------------
# Borradores: rutas estaticas (/draft, /drafts) ANTES de /{survey_id}
# para que FastAPI no las confunda con un id dinamico.
# ---------------------------------------------------------------------------

@router.post(
    "/draft",
    response_model=SurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Guardar un borrador (permite contenido parcial)",
)
def create_draft(
    payload: DraftPayload,
    x_creator_id: Optional[str] = Header(default=None),
):
    creator_id = x_creator_id or _TEST_CREATOR_ID
    try:
        return supabase_service.create_draft(payload, creator_id)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get(
    "/drafts",
    response_model=List[SurveyResponse],
    summary="Listar mis borradores",
)
def list_drafts(x_creator_id: Optional[str] = Header(default=None)):
    creator_id = x_creator_id or _TEST_CREATOR_ID
    return supabase_service.list_drafts(creator_id)


@router.get(
    "/{survey_id}",
    response_model=SurveyResponse,
    summary="Obtener una encuesta por id (incluye preguntas)",
)
def get_survey(survey_id: int):
    survey = supabase_service.get_survey_by_id(survey_id)
    if not survey:
        raise HTTPException(status_code=404, detail="Encuesta no encontrada.")
    return survey


@router.put(
    "/{survey_id}/draft",
    response_model=SurveyResponse,
    summary="Actualizar un borrador existente",
)
def update_draft(
    survey_id: int,
    payload: DraftPayload,
    x_creator_id: Optional[str] = Header(default=None),
):
    creator_id = x_creator_id or _TEST_CREATOR_ID
    try:
        return supabase_service.update_draft(survey_id, payload, creator_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
