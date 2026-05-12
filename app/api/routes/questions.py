from fastapi import APIRouter, HTTPException

from core.config import supabase
from schemas.question import QuestionCreate, QuestionUpdate
from services import supabase_service
from api.deps import assert_survey_in_status

router = APIRouter(prefix="/surveys/{survey_id}/questions", tags=["questions"])


def _ensure_survey_editable(survey_id: int) -> dict:
    """US-04 — Bloquea la edición de preguntas si la encuesta no está en borrador."""
    survey = supabase_service.get_survey(survey_id)
    return assert_survey_in_status(survey)


@router.post("/")
async def add_question(survey_id: int, question: QuestionCreate):
    # US-04: una encuesta publicada es inmutable
    _ensure_survey_editable(survey_id)

    # Validación de límite de 12
    existing = (
        supabase.table("questions")
        .select("id", count="exact")
        .eq("survey_id", survey_id)
        .execute()
    )
    if existing.count >= 12:
        raise HTTPException(status_code=400, detail="Máximo 12 preguntas por encuesta.")

    # Inserción
    res = (
        supabase.table("questions")
        .insert(
            {
                "survey_id": survey_id,
                "content": question.content,
                "question_type": question.question_type.value,
                "options": question.options,
                "position": question.position,
            }
        )
        .execute()
    )

    return res.data


@router.api_route("/{question_id}", methods=["PUT", "PATCH"])
async def update_question(survey_id: int, question_id: int, question: QuestionUpdate):
    # US-04: rechazar cualquier PATCH/PUT sobre preguntas de una encuesta publicada
    _ensure_survey_editable(survey_id)

    updates = question.model_dump(exclude_unset=True, mode="json")
    if not updates:
        raise HTTPException(
            status_code=400, detail="No se enviaron campos para actualizar."
        )

    res = (
        supabase.table("questions")
        .update(updates)
        .eq("id", question_id)
        .eq("survey_id", survey_id)
        .execute()
    )

    if not res.data:
        raise HTTPException(status_code=404, detail="Pregunta no encontrada.")

    return res.data[0]
